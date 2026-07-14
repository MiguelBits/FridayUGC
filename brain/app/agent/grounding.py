"""Vision grounding — Gemma 3 finds tap targets from screenshots (no OpenAI)."""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import get_settings
from ..llm import ChatMessage, get_vision_llm
from .actions import GroundRequest, GroundResponse, ScreenElement

ANCHOR_HINTS: dict[str, str] = {
    "comments_icon": (
        "Instagram Reels RIGHT rail speech-bubble / comments icon "
        "(below the reel heart, above share/audio). NOT the reel like heart. NOT audio disc."
    ),
    "comment_heart": (
        "Small heart/like button on a COMMENT ROW inside the bottom comments sheet "
        "(white sheet over the reel). NOT the big reel like on the right rail."
    ),
    "nav_reels": "Bottom navigation bar Reels tab icon (second from left, clapperboard).",
    "reel_like": "Large heart on Reels right rail to like the video itself.",
}

GROUND_SYSTEM = (
    "You are a mobile UI grounding model. The user sends a phone screenshot and asks "
    "where to tap. Return ONLY valid JSON with pixel coordinates matching SCREEN_SIZE. "
    "Tap the CENTER of the target icon. If unsure, set confidence below 0.5."
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


def _build_ground_prompt(req: GroundRequest) -> str:
    hint = ANCHOR_HINTS.get(req.anchor, req.anchor)
    row_line = ""
    if req.anchor == "comment_heart" and req.row_index > 0:
        row_line = f"Pick the heart for comment row index {req.row_index} (0=top visible comment).\n"
    return (
        "GROUND_TARGET_JSON\n"
        f"ANCHOR: {req.anchor}\n"
        f"DESCRIPTION: {hint}\n"
        f"SCREEN_TYPE: {req.screen_type}\n"
        f"SCREEN_SIZE: {req.screen_width}x{req.screen_height}\n"
        f"{row_line}"
        f"ACCESSIBILITY HINTS:\n{_elements_hint(req.elements)}\n"
        'Return JSON: {"action":"tap"|"like_comment","params":{"x":int,"y":int},'
        '"confidence":0.0-1.0,"reason":"..."}\n'
        "Coordinates must be within SCREEN_SIZE bounds."
    )


def _parse_ground_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\"x\"\s*:\s*\d+[^{}]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _mock_ground(req: GroundRequest) -> GroundResponse:
    w = req.screen_width or 1080
    h = req.screen_height or 2400
    presets = {
        "comments_icon": (int(w * 0.92), int(h * 0.58)),
        "comment_heart": (int(w * 0.86), int(h * (0.58 + 0.07 * req.row_index))),
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

    prompt = _build_ground_prompt(req)
    llm = get_vision_llm()
    try:
        raw = await llm.chat(
            [ChatMessage("system", GROUND_SYSTEM), ChatMessage("user", prompt, images=[shot])],
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
    params = data.get("params") if isinstance(data.get("params"), dict) else data
    if not isinstance(params, dict):
        params = {}
    x = params.get("x") or data.get("x")
    y = params.get("y") or data.get("y")
    try:
        xi, yi = int(x), int(y)
    except (TypeError, ValueError):
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason="ground parse failed — no x,y",
            needs_screenshot=True,
        )

    w = req.screen_width or 9999
    h = req.screen_height or 9999
    if not (0 <= xi <= w and 0 <= yi <= h):
        return GroundResponse(
            action="tap",
            params={},
            confidence=0.0,
            reason=f"coords out of bounds ({xi},{yi})",
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
