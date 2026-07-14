"""Deterministic playbook steps when the LLM or classifier is stuck."""

from __future__ import annotations

from .actions import Screen, ScreenState, StepRequest, StepResponse
from .perception import on_comments_sheet, on_reels_surface
from .prompt import ctx_int, goal_wants_comment_likes


def _screen_size(screen: Screen) -> tuple[int, int]:
    w = h = 0
    for e in screen.elements:
        w = max(w, e.x + e.w)
        h = max(h, e.y + e.h)
    return w, h


def find_comments_target(screen: Screen) -> dict:
    """Comments bubble on reels right rail — element id only; vision if missing."""
    for e in screen.elements:
        t = e.text.lower()
        if "comment" in t and e.clickable:
            return {"target_id": e.id}
        if e.clickable and e.w > 0 and e.h > 0:
            cx = e.x + e.w // 2
            cy = e.y + e.h // 2
            w = max((el.x + el.w for el in screen.elements), default=0)
            if w > 0 and cx > w * 0.75 and 0.35 < cy / max((el.y + el.h for el in screen.elements), default=1) < 0.75:
                return {"target_id": e.id}
    return {}


def find_comment_heart_target(screen: Screen, liked_this_reel: int) -> dict:
    """Comment row heart — icon-only on Instagram; use id hints or right-rail position."""
    w, h = _screen_size(screen)
    candidates: list[tuple[int, int, int]] = []  # id, cy, cx
    for e in screen.elements:
        if not e.clickable:
            continue
        t = e.text.lower()
        cx = e.x + e.w // 2
        cy = e.y + e.h // 2
        if any(k in t for k in ("like", "heart", "favorite", "id:like", "id:heart")):
            candidates.append((e.id, cy, cx))
            continue
        if w > 0 and h > 0 and e.w in range(1, 140) and e.h in range(1, 140):
            if cx > w * 0.70 and 0.12 < cy / h < 0.90:
                candidates.append((e.id, cy, cx))
    if candidates:
        candidates.sort(key=lambda item: item[1])
        idx = min(liked_this_reel, len(candidates) - 1)
        return {"target_id": candidates[idx][0]}
    return {}


def comment_likes_kickstart(req: StepRequest, state: ScreenState) -> StepResponse | None:
    """First action on Reels: open comments sheet."""
    if not goal_wants_comment_likes(req.goal):
        return None
    ctx = req.session_context or {}
    if on_comments_sheet(state, ctx):
        return None
    if not on_reels_surface(state, ctx):
        return None
    if ctx_int(ctx, "comment_likes_this_reel") > 0:
        return None

    params = find_comments_target(req.screen)
    if not params and not (req.screen.screenshot_b64 or "").strip():
        return StepResponse(
            action="wait",
            params={"ms": 300},
            say="Need screenshot to find comments icon.",
            reason="kickstart needs vision",
            done=False,
            needs_screenshot=True,
            approval_required=False,
        )
    if not params:
        return StepResponse(
            action="intent",
            params={"name": "open_comments"},
            say="Opening comments via intent resolver.",
            reason="playbook recovery — no comment element; phone uses vision/memory",
            done=False,
            needs_screenshot=True,
            approval_required=False,
        )

    return StepResponse(
        action="tap",
        params=params,
        say="Opening comments on this reel.",
        reason="playbook kickstart — tap comments icon on reels_viewer",
        done=False,
        needs_screenshot=False,
        approval_required=False,
    )


def comment_likes_like_hearts(req: StepRequest, state: ScreenState) -> StepResponse | None:
    """On comments sheet with budget left — like next comment heart."""
    if not goal_wants_comment_likes(req.goal):
        return None
    ctx = req.session_context or {}
    if not on_comments_sheet(state, ctx):
        return None
    per_reel = ctx_int(ctx, "comment_likes_per_reel", 5)
    this_reel = ctx_int(ctx, "comment_likes_this_reel")
    if this_reel >= per_reel:
        return StepResponse(
            action="press",
            params={"key": "back"},
            say="Done with this reel's comments.",
            reason="per-reel comment like budget met",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )
    params = find_comment_heart_target(req.screen, this_reel)
    if not params:
        return StepResponse(
            action="intent",
            params={"name": "engage_comments"},
            say="Engaging comments via intent.",
            reason="playbook recovery — need vision for comment hearts",
            done=False,
            needs_screenshot=True,
            approval_required=False,
        )
    return StepResponse(
        action="like_comment",
        params=params,
        say=f"Liking comment {this_reel + 1}/{per_reel}.",
        reason="playbook — heart on comment row",
        done=False,
        needs_screenshot=False,
        approval_required=False,
    )
