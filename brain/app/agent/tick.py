"""POST /agent/tick — brain-owned observe→verify→plan→ground loop."""

from __future__ import annotations

import logging

from .actions import LastResult, StepRequest, TickRequest, TickResponse
from .motor_resolver import resolve_intent_step_async, resolve_plan
from .perception import classify_screen
from .router import decide
from .routines import apply_verified_action, comment_likes_plan, plan_to_step_response
from .session_store import SessionStore
from .verifier import verify_last

logger = logging.getLogger(__name__)
_store = SessionStore()


async def handle_tick(req: TickRequest) -> TickResponse:
    session = _store.load(
        req.session_id,
        goal=req.goal,
        device_id=req.device_id,
        seed=req.session_context or None,
    )
    ctx = session["context"]
    screen = req.observe.screen
    activity = screen.activity or ""
    state = classify_screen(screen)

    # --- verify previous action ---
    if req.last_result and req.last_result.action:
        verified, score = verify_last(req.last_result, activity)
        req.last_result.verified = verified
        req.last_result.change_score = score

        ui_key = req.last_result.ui_key or str(req.last_result.params.get("ui_key", ""))
        counts = (
            verified == "verified"
            or req.last_result.action not in {"tap", "like_comment"}
            or (req.last_result.executor_ok and verified != "failed")
        )
        if req.last_result.executor_ok and counts:
            apply_verified_action(
                ctx,
                req.last_result.action,
                verified,
                req.last_result.params,
                executor_ok=req.last_result.executor_ok,
            )
            if verified == "verified" and ui_key:
                _store.reset_anchor_retry(req.session_id, ui_key)
            _store.append_history(req.session_id, f"{req.last_result.action}({verified})")
        elif req.last_result.executor_ok and ui_key:
            streak = _store.bump_anchor_retry(req.session_id, ui_key)
            _store.append_history(req.session_id, f"{req.last_result.action}(unverified#{streak})")
            if streak >= 3 and ui_key == "comments_icon":
                ctx["comment_likes_phase"] = "on_reels"
                ctx["comments_sheet_open"] = 0
                ctx["comment_likes_this_reel"] = 0
                ctx["comment_likes_this_reel_target"] = 0
                ctx["reel_dwell_done"] = 0
                ctx["ready_for_next_reel"] = 1

    # --- plan next action ---
    grounded = False
    plan = comment_likes_plan(ctx, screen, state) if str(ctx.get("phase")) == "reels_comment_likes" else None

    if plan:
        if plan.kind == "ground_tap":
            step, grounded = await resolve_plan(plan, req.observe, req.device_id, state.screen_type)
        else:
            step = plan_to_step_response(plan)
    else:
        step_req = StepRequest(
            session_id=req.session_id,
            goal=req.goal,
            step=req.step,
            screen=screen,
            last_result=None,
            history=session["history"],
            mode=req.mode,
            device_id=req.device_id,
            screen_state=state,
            session_context=ctx,
        )
        if req.last_result:
            step_req.last_result = LastResult(
                action=req.last_result.action,
                ok=req.last_result.executor_ok,
                error=req.last_result.error,
                verified=req.last_result.verified,
                change_score=req.last_result.change_score,
            )
        step = await decide(step_req)
        if step.action == "intent":
            row = int(ctx.get("comment_likes_this_reel", 0))
            step, grounded = await resolve_intent_step_async(
                step, req.observe, req.device_id, state.screen_type, row_index=row
            )

    _store.save(req.session_id, req.goal, req.device_id)

    resp = TickResponse(
        action=step.action,
        params=step.params,
        say=step.say,
        reason=step.reason,
        done=step.done,
        needs_screenshot=step.needs_screenshot,
        approval_required=step.approval_required,
        session_context=ctx,
        grounded=grounded,
    )
    logger.info(
        "tick session=%s step=%s action=%s grounded=%s reason=%s phase=%s reels_tab=%s entry_try=%s",
        req.session_id[:8],
        req.step,
        resp.action,
        grounded,
        (resp.reason or "")[:120],
        ctx.get("phase"),
        ctx.get("reels_tab_opened"),
        ctx.get("reels_entry_attempts"),
    )
    print(
        f"TICK step={req.step} action={resp.action} grounded={grounded} "
        f"reels_tab={ctx.get('reels_tab_opened')} entry={ctx.get('reels_entry_attempts')} "
        f"reason={(resp.reason or '')[:100]}",
        flush=True,
    )
    return resp
