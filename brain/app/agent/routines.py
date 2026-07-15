"""Comment-likes and routine FSM — brain-owned choreography."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .actions import Screen, ScreenState, StepResponse
from .perception import classify_screen, is_full_comments_sheet, on_reels_surface

PHASE_ON_REELS = "on_reels"
PHASE_IN_COMMENTS = "in_comments"
PHASE_CLOSING = "closing"

LIKES_PER_SCROLL = 2
MAX_SHEET_SCROLLS = 3


@dataclass
class MotorPlan:
    """Internal plan step before vision grounding."""

    kind: str  # ground_tap | motor | done
    anchor: str = ""
    action: str = "tap"
    params: dict[str, Any] | None = None
    say: str = ""
    reason: str = ""
    done: bool = False
    row_index: int = 0


def _ctx_int(ctx: dict, key: str, default: int = 0) -> int:
    try:
        return int(ctx.get(key, default))
    except (TypeError, ValueError):
        return default


def apply_verified_action(
    ctx: dict[str, Any],
    action: str,
    verified: str,
    params: dict | None = None,
    *,
    executor_ok: bool = True,
) -> None:
    """Update session context after a verified (or soft-counted) step."""
    params = params or {}
    soft_motor = executor_ok and action in {
        "navigate",
        "open_reels",
        "swipe",
        "scroll",
        "press",
        "wait",
    }
    ok = verified in {"verified", "unknown"} or soft_motor
    if not ok:
        return

    if action == "like_comment":
        ctx["comment_likes_used"] = _ctx_int(ctx, "comment_likes_used") + 1
        ctx["comment_likes_this_reel"] = _ctx_int(ctx, "comment_likes_this_reel") + 1
        ctx["comment_likes_since_scroll"] = _ctx_int(ctx, "comment_likes_since_scroll") + 1
    elif action == "tap":
        ui = str(params.get("ui_key", ""))
        if ui == "comments_icon":
            ctx["comments_sheet_open"] = 1
            ctx["comment_likes_phase"] = PHASE_IN_COMMENTS
            ctx["comment_likes_since_scroll"] = 0
            ctx["comment_sheet_scrolls"] = 0
    elif action == "scroll" and str(params.get("zone", "")).lower() == "comments_sheet":
        ctx["comment_likes_since_scroll"] = 0
        ctx["comment_sheet_scrolls"] = _ctx_int(ctx, "comment_sheet_scrolls") + 1
    elif action == "press" and str(params.get("key", "")).lower() == "back":
        ctx["comments_sheet_open"] = 0
        ctx["comment_likes_this_reel"] = 0
        ctx["comment_likes_since_scroll"] = 0
        ctx["comment_sheet_scrolls"] = 0
        ctx["comment_likes_phase"] = PHASE_ON_REELS
        ctx["ready_for_next_reel"] = 1
    elif action == "swipe" and str(params.get("zone", "")).lower() == "reels_rail":
        ctx["reels_scrolled"] = _ctx_int(ctx, "reels_scrolled") + 1
        ctx["comments_sheet_open"] = 0
        ctx["comment_likes_this_reel"] = 0
        ctx["comment_likes_since_scroll"] = 0
        ctx["comment_sheet_scrolls"] = 0
        ctx["comment_likes_phase"] = PHASE_ON_REELS
        ctx["ready_for_next_reel"] = 0
    elif action in {"navigate", "open_reels"}:
        ctx["reels_tab_opened"] = 1
        ctx["reels_entry_attempts"] = _ctx_int(ctx, "reels_entry_attempts") + 1


def comment_likes_plan(ctx: dict[str, Any], screen: Screen, state: ScreenState) -> MotorPlan | None:
    if str(ctx.get("phase", "")) != "reels_comment_likes":
        return None

    if _ctx_int(ctx, "comment_likes_used") >= _ctx_int(ctx, "comment_likes_max", 50):
        return MotorPlan(
            kind="done",
            done=True,
            say="Comment-likes budget complete.",
            reason="comment_likes_max",
        )

    phase = str(ctx.get("comment_likes_phase", PHASE_ON_REELS))
    activity = screen.activity or state.activity_class or ""

    if phase == PHASE_CLOSING:
        return MotorPlan(
            kind="motor",
            action="press",
            params={"key": "back"},
            say="Closing comments.",
            reason="routine closing",
        )

    if phase == PHASE_IN_COMMENTS:
        per_reel = _ctx_int(ctx, "comment_likes_per_reel", 5)
        this_reel = _ctx_int(ctx, "comment_likes_this_reel")
        if this_reel >= per_reel:
            ctx["comment_likes_phase"] = PHASE_CLOSING
            return MotorPlan(
                kind="motor",
                action="press",
                params={"key": "back"},
                say="Closing comments.",
                reason="per-reel budget met",
            )

        since_scroll = _ctx_int(ctx, "comment_likes_since_scroll")
        sheet_scrolls = _ctx_int(ctx, "comment_sheet_scrolls")
        if since_scroll >= LIKES_PER_SCROLL and sheet_scrolls < MAX_SHEET_SCROLLS and this_reel < per_reel:
            return MotorPlan(
                kind="motor",
                action="scroll",
                params={"direction": "up", "zone": "comments_sheet"},
                say="Scrolling comments for more hearts.",
                reason="routine scroll sheet",
            )

        if this_reel > 0 and since_scroll >= LIKES_PER_SCROLL and sheet_scrolls >= MAX_SHEET_SCROLLS:
            ctx["comment_likes_phase"] = PHASE_CLOSING
            return MotorPlan(
                kind="motor",
                action="press",
                params={"key": "back"},
                say="Closing comments.",
                reason="done liking visible rows",
            )

        return MotorPlan(
            kind="ground_tap",
            anchor="comment_heart",
            action="like_comment",
            say=f"Like comment {this_reel + 1}/{per_reel}.",
            reason="routine like comment heart",
            row_index=this_reel,
        )

    # PHASE_ON_REELS — deeplink first; vision only while entry not yet attempted
    entry_attempts = _ctx_int(ctx, "reels_entry_attempts")
    on_reels = on_reels_surface(state, ctx, screen)
    if not on_reels and not is_full_comments_sheet(screen, activity):
        if entry_attempts >= 2:
            ctx["reels_tab_opened"] = 1
        elif not _ctx_int(ctx, "reels_tab_opened"):
            return MotorPlan(
                kind="motor",
                action="open_reels",
                params={"ui_key": "nav_reels"},
                say="Opening Reels.",
                reason="routine enter reels deeplink",
            )
        elif entry_attempts < 2:
            return MotorPlan(
                kind="ground_tap",
                anchor="nav_reels",
                action="tap",
                say="Opening Reels.",
                reason="routine enter reels vision retry",
            )
        # entry_attempts >= 2: proceed to comments even if classifier unsure

    if _ctx_int(ctx, "ready_for_next_reel"):
        ctx["ready_for_next_reel"] = 0
        if _ctx_int(ctx, "reels_scrolled") >= _ctx_int(ctx, "reels_max", 10):
            return MotorPlan(kind="done", done=True, say="Comment-likes complete.", reason="reels_max")
        return MotorPlan(
            kind="motor",
            action="swipe",
            params={"direction": "up", "zone": "reels_rail"},
            say="Next reel.",
            reason="routine next reel",
        )

    if is_full_comments_sheet(screen, activity) or _ctx_int(ctx, "comments_sheet_open"):
        ctx["comment_likes_phase"] = PHASE_IN_COMMENTS
        ctx["comments_sheet_open"] = 1
        return comment_likes_plan(ctx, screen, state)

    return MotorPlan(
        kind="ground_tap",
        anchor="comments_icon",
        action="tap",
        say="Open comments.",
        reason="routine open comments",
    )


def plan_to_step_response(plan: MotorPlan) -> StepResponse:
    if plan.kind == "done":
        return StepResponse(action="done", say=plan.say, reason=plan.reason, done=True)
    if plan.kind == "motor":
        return StepResponse(
            action=plan.action,  # type: ignore[arg-type]
            params=plan.params or {},
            say=plan.say,
            reason=plan.reason,
        )
    return StepResponse(
        action="wait",
        params={"ms": 300},
        say=plan.say,
        reason=plan.reason,
        needs_screenshot=True,
    )
