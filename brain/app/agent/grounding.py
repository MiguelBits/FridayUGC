"""Vision grounding — Gemma 3 finds tap targets from screenshots (Set-of-Marks + coords)."""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from ..config import get_settings
from ..learning.grounding_examples import format_exemplar_hints
from ..learning.store import LearningStore
from ..llm import ChatMessage, get_vision_llm
from .actions import GroundRequest, GroundResponse, ScreenElement, SomMark

ANCHOR_HINTS: dict[str, str] = {
    "comments_icon": (
        "Instagram Reels speech-bubble / comments icon on the RIGHT rail — "
        "the icon DIRECTLY BELOW the reel heart/like button. NOT share. NOT audio disc."
    ),
    "comment_heart": (
        "Small heart/like button on a COMMENT ROW inside the bottom comments sheet "
        "(white sheet over the reel). NOT the big reel like on the right rail."
    ),
    "nav_reels": "Bottom navigation bar Reels tab icon (second from left, clapperboard).",
    "reel_like": "Large heart on Reels right rail to like the video itself.",
}

GROUND_SYSTEM = (
    "You are a mobile UI grounding model. The user sends a phone screenshot (often with "
    "numbered Set-of-Marks overlays on interactive elements) and asks where to tap. "
    "Return ONLY valid JSON. Prefer mark_id when SOM_MARKS are listed; otherwise use x,y pixels."
)

GROUND_SYSTEM_SOM = (
    "You are a mobile UI grounding model. The screenshot has numbered orange boxes (Set-of-Marks). "
    "Pick the mark_id whose labeled element best matches the ANCHOR description. "
    "Return ONLY JSON: {\"mark_id\":int,\"confidence\":0.0-1.0,\"reason\":\"...\"}"
)


def _elements_hint(elements: list[ScreenElement]) -> str:
    if not elements:
        return "(no accessibility elements — rely on image only)"
    lines = []
    for e in elements[:40]:
        cx = e.x + e.w // 2 if e.w else e.x
        cy = e.y + e.h // 2 if e.h else e.y
        lines.append(f"  id={e.id} text={e.text!r} center={cx},{cy} clickable={e.clickable}")
    return "\n".join(lines)


def _som_hint(marks: list[SomMark]) -> str:
    if not marks:
        return "(no Set-of-Marks — use pixel coordinates)"
    lines = []
    for m in marks[:25]:
        label = f" text={m.text!r}" if m.text else ""
        lines.append(f"  mark_id={m.mark_id} center={m.x},{m.y}{label}")
    return "\n".join(lines)


def _decode_image_size(screenshot_b64: str) -> tuple[int, int]:
    """Return (width, height) of the JPEG sent to the vision model."""
    try:
        from PIL import Image

        raw = base64.b64decode(screenshot_b64, validate=False)
        with Image.open(io.BytesIO(raw)) as img:
            return img.size
    except (ValueError, OSError, ImportError):
        return 0, 0


def _rescale_coords(
    x: int,
    y: int,
    img_w: int,
    img_h: int,
    screen_w: int,
    screen_h: int,
) -> tuple[int, int]:
    """Map model coords from encoded image space to device display pixels."""
    if img_w <= 0 or img_h <= 0 or screen_w <= 0 or screen_h <= 0:
        return x, y
    if img_w == screen_w and img_h == screen_h:
        return x, y
    sx = screen_w / img_w
    sy = screen_h / img_h
    return int(round(x * sx)), int(round(y * sy))


def _build_ground_prompt(req: GroundRequest, image_w: int = 0, image_h: int = 0) -> str:
    hint = ANCHOR_HINTS.get(req.anchor, req.anchor)
    row_line = ""
    if req.anchor == "comment_heart" and req.row_index > 0:
        row_line = f"Pick the heart for comment row index {req.row_index} (0=top visible comment).\n"
    exemplars = format_exemplar_hints(
        LearningStore().grounding_examples(req.anchor, device_id=req.device_id, limit=5)
    )
    image_line = ""
    if image_w > 0 and image_h > 0:
        image_line = f"IMAGE_SIZE: {image_w}x{image_h}\n"
    use_som = req.use_som and len(req.som_marks) > 0
    if use_som:
        return (
            "GROUND_TARGET_SOM_JSON\n"
            f"ANCHOR: {req.anchor}\n"
            f"DESCRIPTION: {hint}\n"
            f"SCREEN_TYPE: {req.screen_type}\n"
            f"{row_line}"
            f"{exemplars}"
            f"SOM_MARKS (numbered boxes on image):\n{_som_hint(req.som_marks)}\n"
            'Return JSON: {"mark_id":int,"confidence":0.0-1.0,"reason":"..."}\n'
        )
    return (
        "GROUND_TARGET_JSON\n"
        f"ANCHOR: {req.anchor}\n"
        f"DESCRIPTION: {hint}\n"
        f"SCREEN_TYPE: {req.screen_type}\n"
        f"SCREEN_SIZE: {req.screen_width}x{req.screen_height}\n"
        f"{image_line}"
        f"{row_line}"
        f"{exemplars}"
        f"ACCESSIBILITY HINTS:\n{_elements_hint(req.elements)}\n"
        'Return JSON: {"action":"tap"|"like_comment","params":{"x":int,"y":int},'
        '"confidence":0.0-1.0,"reason":"..."}\n'
        "Return x,y in SCREEN_SIZE (device display) pixel coordinates."
    )


def _resolve_mark(mark_id: int, marks: list[SomMark]) -> tuple[int, int] | None:
    for m in marks:
        if m.mark_id == mark_id:
            return m.x, m.y
    return None


def _pick_mock_mark(req: GroundRequest) -> int | None:
    """Heuristic mark selection for mock provider."""
    if not req.som_marks:
        return None
    anchor = req.anchor
    if anchor == "comments_icon":
        h = req.screen_height or 2400
        w = req.screen_width or 1080
        band = [
            m for m in req.som_marks
            if m.x > w * 0.78 and h * 0.47 <= m.y <= h * 0.57
        ]
        if band:
            band.sort(key=lambda m: abs(m.y - h * 0.52))
            return band[0].mark_id
        sorted_m = sorted(req.som_marks, key=lambda m: (-m.x, m.y))
        return sorted_m[0].mark_id if sorted_m else None
    if anchor == "comment_heart":
        w = req.screen_width or 1080
        h = req.screen_height or 2400
        sheet = [
            m for m in req.som_marks
            if m.y > h * 0.58 and m.x < w * 0.22
        ]
        sheet.sort(key=lambda m: m.y)
        idx = min(req.row_index, len(sheet) - 1) if sheet else 0
        return sheet[idx].mark_id if sheet else req.som_marks[0].mark_id
    return req.som_marks[0].mark_id


def _parse_ground_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            chunk = part.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                text = chunk
                break
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Largest brace-balanced object (handles nested params.x/y).
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
    m = re.search(r"\{[^{}]*(\"mark_id\"|\"x\")\s*:\s*\d+[^{}]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _parse_coord(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _comments_icon_band_ok(xi: int, yi: int, w: int, h: int) -> bool:
    """comments_icon rail band — relaxed for device variance."""
    if w <= 0 or h <= 0:
        return True
    if xi > w * 0.78 and yi >= h * 0.62:
        return False
    if xi > w * 0.78 and not (h * 0.45 <= yi <= h * 0.60):
        return False
    return True


def _mock_ground(req: GroundRequest) -> GroundResponse:
    if req.use_som and req.som_marks:
        mark_id = _pick_mock_mark(req)
        if mark_id is not None:
            coords = _resolve_mark(mark_id, req.som_marks)
            if coords:
                x, y = coords
                action = "like_comment" if req.anchor == "comment_heart" else "tap"
                return GroundResponse(
                    action=action,
                    params={"x": x, "y": y, "mark_id": mark_id},
                    confidence=0.8,
                    reason=f"mock som mark {mark_id} for {req.anchor}",
                )
    w = req.screen_width or 1080
    h = req.screen_height or 2400
    presets = {
        "comments_icon": (int(w * 0.90), int(h * 0.56)),
        "comment_heart": (int(w * 0.12), int(h * (0.68 + 0.075 * req.row_index))),
        "nav_reels": (int(w * 0.30), int(h * 0.93)),
        "reel_like": (int(w * 0.92), int(h * 0.48)),
    }
    x, y = presets.get(req.anchor, (w // 2, h // 2))
    action = "like_comment" if req.anchor == "comment_heart" else "tap"
    return GroundResponse(
        action=action,
        params={"x": x, "y": y},
        confidence=0.75,
        reason=f"mock ground for {req.anchor}",
    )


async def ground_target(req: GroundRequest) -> GroundResponse:
    """Find tap coordinates from screenshot using local Gemma 3 vision."""
    settings = get_settings()
    if not settings.grounding_enabled:
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason="grounding disabled",
            needs_screenshot=True,
        )

    shot = (req.screenshot_b64 or "").strip()
    if not shot:
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason="grounding needs screenshot",
            needs_screenshot=True,
        )

    if settings.llm_provider.lower() == "mock":
        return _mock_ground(req)

    if not settings.vision_enabled:
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason="vision disabled",
            needs_screenshot=True,
        )

    img_w, img_h = _decode_image_size(shot)
    use_som = req.use_som and len(req.som_marks) > 0
    system = GROUND_SYSTEM_SOM if use_som else GROUND_SYSTEM
    prompt = _build_ground_prompt(req, image_w=img_w, image_h=img_h)
    llm = get_vision_llm()
    try:
        raw = await llm.chat(
            [ChatMessage("system", system), ChatMessage("user", prompt, images=[shot])],
            json_mode=True,
            temperature=0.2,
            max_tokens=256,
        )
    except Exception as exc:
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason=f"vision ground failed: {exc}",
            needs_screenshot=True,
        )

    data = _parse_ground_json(raw)

    if use_som:
        mark_id = data.get("mark_id")
        try:
            mid = int(mark_id)
        except (TypeError, ValueError):
            return GroundResponse(
                action="tap",
                params={},
                confidence=0.0,
                reason="som parse failed — no mark_id",
                needs_screenshot=True,
            )
        coords = _resolve_mark(mid, req.som_marks)
        if not coords:
            return GroundResponse(
                action="tap",
                params={},
                confidence=0.0,
                reason=f"unknown mark_id {mid}",
                needs_screenshot=True,
            )
        xi, yi = coords
        sw = req.screen_width or 1080
        sh = req.screen_height or 2400
        if req.anchor == "comments_icon" and not _comments_icon_band_ok(xi, yi, sw, sh):
            return GroundResponse(
                action="tap",
                params={},
                confidence=0.0,
                reason=f"som mark outside comments band ({xi},{yi})",
                needs_screenshot=True,
            )
        action = "like_comment" if req.anchor == "comment_heart" else "tap"
        try:
            conf = float(data.get("confidence", 0.75))
        except (TypeError, ValueError):
            conf = 0.75
        return GroundResponse(
            action=action,
            params={"x": xi, "y": yi, "mark_id": mid},
            confidence=conf,
            reason=str(data.get("reason", f"som mark {mid} for {req.anchor}")),
        )

    params = data.get("params") if isinstance(data.get("params"), dict) else data
    if not isinstance(params, dict):
        params = {}
    xi = _parse_coord(params.get("x") if params.get("x") is not None else data.get("x"))
    yi = _parse_coord(params.get("y") if params.get("y") is not None else data.get("y"))
    if xi is None or yi is None:
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason="ground parse failed — no x,y",
            needs_screenshot=True,
        )

    sw = req.screen_width or 9999
    sh = req.screen_height or 9999
    xi, yi = _rescale_coords(xi, yi, img_w, img_h, sw, sh)

    if not (0 <= xi <= sw and 0 <= yi <= sh):
        if img_w > 0 and img_h > 0 and (xi > sw or yi > sh):
            xi = max(0, min(xi, sw))
            yi = max(0, min(yi, sh))
        else:
            return GroundResponse(
                action="tap",
                params={},
                confidence=0.0,
                reason=f"coords out of bounds ({xi},{yi})",
                needs_screenshot=True,
            )
    if req.anchor == "comments_icon" and not _comments_icon_band_ok(xi, yi, sw, sh):
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason=f"comments_icon coords outside comments band ({xi},{yi})",
            needs_screenshot=True,
        )

    action = str(data.get("action", "like_comment" if req.anchor == "comment_heart" else "tap"))
    if action not in {"tap", "like_comment"}:
        action = "like_comment" if req.anchor == "comment_heart" else "tap"
    try:
        conf = float(data.get("confidence", 0.7))
    except (TypeError, ValueError):
        conf = 0.7

    return GroundResponse(
        action=action,
        params={"x": xi, "y": yi},
        confidence=conf,
        reason=str(data.get("reason", f"grounded {req.anchor}")),
    )
