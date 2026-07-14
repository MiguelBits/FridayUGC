"""Recovery playbook — a11y binding only; vision via intent when tree is sparse."""

from __future__ import annotations

from .actions import Screen, ScreenState, StepRequest, StepResponse
from .perception import on_comments_sheet, on_reels_surface
from .prompt import ctx_int, goal_wants_comment_likes

REEL_LIKE_Y_MAX = 0.54
SHEET_MIN_Y = 0.55


def _screen_size(screen: Screen) -> tuple[int, int]:
    w = h = 0
    for e in screen.elements:
        w = max(w, e.x + e.w)
        h = max(h, e.y + e.h)
    return w, h


def find_comments_target(screen: Screen) -> dict:
    """Comments bubble — element id from a11y only."""
    w, h = _screen_size(screen)
    min_y = int(h * REEL_LIKE_Y_MAX) if h else 0
    max_y = int(h * 0.72) if h else 0
    min_x = int(w * 0.78) if w else 0
    for e in screen.elements:
        if not e.clickable:
            continue
        t = e.text.lower()
        cx = e.x + e.w // 2
        cy = e.y + e.h // 2
        if "comment" in t:
            return {"target_id": e.id}
        if w > 0 and h > 0 and cx >= min_x and min_y <= cy <= max_y:
            return {"target_id": e.id}
    return {}


def find_comment_heart_target(screen: Screen, liked_this_reel: int) -> dict:
    """Comment row heart — element id from a11y only."""
    w, h = _screen_size(screen)
    if w == 0 or h == 0:
        return {}
    sheet_min_y = int(h * SHEET_MIN_Y)
    reel_max_y = int(h * REEL_LIKE_Y_MAX)
    candidates: list[tuple[int, int]] = []
    for e in screen.elements:
        if not e.clickable or e.w <= 0 or e.h <= 0:
            continue
        cx = e.x + e.w // 2
        cy = e.y + e.h // 2
        if cy < sheet_min_y:
            continue
        if cx > w * 0.88 and cy < reel_max_y:
            continue
        t = e.text.lower()
        if any(k in t for k in ("like", "heart", "favorite", "id:like")) or (
            e.w <= 120 and e.h <= 120 and cx > w * 0.72
        ):
            candidates.append((e.id, cy))
    if candidates:
        candidates.sort(key=lambda item: item[1])
        idx = min(liked_this_reel, len(candidates) - 1)
        return {"target_id": candidates[idx][0]}
    return {}


def comment_likes_kickstart(req: StepRequest, state: ScreenState) -> StepResponse | None:
    if not goal_wants_comment_likes(req.goal):
        return None
    ctx = req.session_context or {}
    phase = str(ctx.get("comment_likes_phase", "on_reels"))
    if phase != "on_reels" or on_comments_sheet(state, ctx):
        return None
    if not on_reels_surface(state, ctx, req.screen):
        return None
    if ctx_int(ctx, "comment_likes_this_reel") > 0:
        return None
    params = find_comments_target(req.screen)
    if params:
        return StepResponse(
            action="tap",
            params=params,
            say="Opening comments on this reel.",
            reason="playbook recovery — a11y comments target",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )
    if not (req.screen.screenshot_b64 or "").strip():
        return StepResponse(
            action="intent",
            params={"name": "open_comments"},
            say="Need vision to open comments.",
            reason="playbook recovery — request screenshot for grounding",
            done=False,
            needs_screenshot=True,
            approval_required=False,
        )
    return StepResponse(
        action="intent",
        params={"name": "open_comments"},
        say="Opening comments via vision.",
        reason="playbook recovery — ground comments icon",
        done=False,
        needs_screenshot=False,
        approval_required=False,
    )


def comment_likes_like_hearts(req: StepRequest, state: ScreenState) -> StepResponse | None:
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
            say="Closing comments — per-reel budget met.",
            reason="playbook recovery — close comments",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )
    params = find_comment_heart_target(req.screen, this_reel)
    if params:
        return StepResponse(
            action="like_comment",
            params=params,
            say=f"Liking comment {this_reel + 1}/{per_reel}.",
            reason="playbook recovery — a11y heart",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )
    return StepResponse(
        action="intent",
        params={"name": "engage_comments"},
        say="Finding comment hearts via vision.",
        reason="playbook recovery — ground comment heart",
        done=False,
        needs_screenshot=not bool((req.screen.screenshot_b64 or "").strip()),
        approval_required=False,
    )
