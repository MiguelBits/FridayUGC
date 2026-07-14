"""Deterministic playbook — zone constants match Android CommentLikesRoutine."""

from __future__ import annotations

from .actions import Screen, ScreenState, StepRequest, StepResponse
from .perception import on_comments_sheet, on_reels_surface
from .prompt import ctx_int, goal_wants_comment_likes

# Reels rail: like ~48% y, comments ~61% y. Sheet hearts: y > 55%.
REEL_LIKE_Y_MAX = 0.54
COMMENTS_ICON_Y = 0.58
RAIL_X = 0.92
SHEET_MIN_Y = 0.55
COMMENT_HEART_X = 0.86


def _screen_size(screen: Screen) -> tuple[int, int]:
    w = h = 0
    for e in screen.elements:
        w = max(w, e.x + e.w)
        h = max(h, e.y + e.h)
    return w, h


def find_comments_target(screen: Screen) -> dict:
    w, h = _screen_size(screen)
    if w == 0 or h == 0:
        return {"x": 980, "y": 1100}
    min_y = int(h * REEL_LIKE_Y_MAX)
    max_y = int(h * 0.72)
    min_x = int(w * 0.78)
    for e in screen.elements:
        if not e.clickable:
            continue
        t = e.text.lower()
        cx = e.x + e.w // 2
        cy = e.y + e.h // 2
        if "comment" in t:
            return {"target_id": e.id}
        if cx >= min_x and min_y <= cy <= max_y:
            return {"target_id": e.id}
    return {"x": int(w * RAIL_X), "y": int(h * COMMENTS_ICON_Y)}


def find_comment_heart_target(screen: Screen, liked_this_reel: int) -> dict:
    w, h = _screen_size(screen)
    if w == 0 or h == 0:
        row = min(liked_this_reel, 4)
        return {"x": 980, "y": int(2400 * (SHEET_MIN_Y + 0.07 * row + 0.03))}
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
    row = min(liked_this_reel, 4)
    return {
        "x": int(w * COMMENT_HEART_X),
        "y": int(h * (SHEET_MIN_Y + 0.07 * row + 0.03)),
    }


def comment_likes_kickstart(req: StepRequest, state: ScreenState) -> StepResponse | None:
    if not goal_wants_comment_likes(req.goal):
        return None
    ctx = req.session_context or {}
    phase = str(ctx.get("comment_likes_phase", "on_reels"))
    if phase != "on_reels" or on_comments_sheet(state, ctx):
        return None
    if not on_reels_surface(state, ctx):
        return None
    if ctx_int(ctx, "comment_likes_this_reel") > 0:
        return None
    params = find_comments_target(req.screen)
    return StepResponse(
        action="tap",
        params=params,
        say="Opening comments on this reel.",
        reason="playbook open_comments — below reel-like zone",
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
            say="Closing comments — 5 likes done.",
            reason="playbook close_comments",
            done=False,
            needs_screenshot=False,
            approval_required=False,
        )
    params = find_comment_heart_target(req.screen, this_reel)
    return StepResponse(
        action="like_comment",
        params=params,
        say=f"Liking comment {this_reel + 1}/{per_reel}.",
        reason="playbook in_comments — sheet heart only",
        done=False,
        needs_screenshot=False,
        approval_required=False,
    )
