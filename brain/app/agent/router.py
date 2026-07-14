from __future__ import annotations

import time
from datetime import datetime, timezone

from ..config import get_settings
from ..llm import ChatMessage, get_llm, get_vision_llm
from ..operator.service import OperatorService
from ..persona import get_persona
from ..runs import RunStore, StepTrace
from .actions import StepRequest, StepResponse
from .playbook import comment_likes_kickstart, comment_likes_like_hearts
from .perception import resolve_state
from .prompt import (
    apply_guards,
    build_step_user_prompt,
    detect_loop,
    fallback_step_data,
    goal_wants_comment_likes,
    goal_wants_instagram,
    on_instagram,
    parse_step_json,
    response_from_json,
)

INSTAGRAM_UI_SCREENS = frozenset({
    "reels_viewer", "comments_sheet", "home_feed", "unknown", "story_viewer",
})


def _instagram_needs_screenshot(req: StepRequest) -> bool:
    """Vision-by-default for Reels/comment-likes work — not generic feed scroll tests."""
    settings = get_settings()
    if not settings.vision_always_instagram or not settings.vision_enabled:
        return False
    if (req.screen.screenshot_b64 or "").strip():
        return False
    if not on_instagram(req.screen.app or "") and not goal_wants_instagram(req.goal):
        return False
    state = resolve_state(req)
    g = req.goal.lower()
    if state.screen_type in {"reels_viewer", "comments_sheet"}:
        return True
    if goal_wants_comment_likes(req.goal) or "reel" in g:
        return state.screen_type in INSTAGRAM_UI_SCREENS
    return False


def _instagram_ui_step(req: StepRequest) -> bool:
    if not on_instagram(req.screen.app or "") and not goal_wants_instagram(req.goal):
        return False
    state = resolve_state(req)
    return state.screen_type in INSTAGRAM_UI_SCREENS


def _should_use_playbook(req: StepRequest) -> bool:
    """Playbook is recovery-only — not routine choreography."""
    if not goal_wants_comment_likes(req.goal):
        return False
    lr = req.last_result
    if lr and (not lr.ok or lr.verified in {"failed", "unverified"}):
        return True
    return detect_loop(req.history)


def _is_ambiguous_step(req: StepRequest) -> bool:
    settings = get_settings()
    if not settings.vision_on_ambiguous or not settings.vision_enabled:
        return False
    if (req.screen.screenshot_b64 or "").strip():
        return False
    if settings.vision_always_instagram and _instagram_needs_screenshot(req):
        return True
    if goal_wants_comment_likes(req.goal):
        return True
    lr = req.last_result
    if lr and (not lr.ok or lr.verified in {"failed", "unverified"}):
        return True
    if not on_instagram(req.screen.app or ""):
        return False
    n = len(req.screen.elements)
    if 2 <= n < settings.vision_ambiguous_element_threshold:
        return True
    return False


def _vision_capture_response(req: StepRequest) -> StepResponse:
    return StepResponse(
        action="wait",
        params={"ms": 300},
        say="Need screenshot for this screen.",
        reason="vision_on_ambiguous",
        done=False,
        needs_screenshot=True,
        approval_required=False,
    )


def _guard_info(req: StepRequest, raw: StepResponse, guarded: StepResponse) -> tuple[bool, str]:
    if raw.action != guarded.action:
        return True, guarded.reason or f"action changed {raw.action} -> {guarded.action}"
    if req.mode == "read_only" and guarded.reason and "Blocked" in guarded.reason:
        return True, guarded.reason
    if guarded.reason and "budget hit" in guarded.reason.lower():
        return True, guarded.reason
    return False, ""


def _record_step(
    req: StepRequest,
    resp: StepResponse,
    *,
    latency_ms: float,
    guard_triggered: bool,
    guard_reason: str,
) -> None:
    settings = get_settings()
    trace = StepTrace(
        step=req.step,
        goal=req.goal,
        foreground_app=req.screen.app,
        action=resp.action,
        approval_required=resp.approval_required,
        guard_triggered=guard_triggered,
        guard_reason=guard_reason,
        latency_ms=round(latency_ms, 2),
        provider=settings.llm_provider,
        at=datetime.now(timezone.utc).isoformat(),
    )
    terminal = resp.done or resp.action == "done"
    failed = resp.action == "fail"
    RunStore().record_step(
        session_id=req.session_id,
        goal=req.goal,
        trace=trace,
        terminal=terminal,
        failed=failed,
    )


async def decide(req: StepRequest, persona_key: str = "lorena") -> StepResponse:
    """Route to legacy LLM loop or Microsoft Agent Framework."""
    engine = get_settings().agent_engine.lower()
    if engine == "maf":
        from .maf_loop import decide_maf

        return await decide_maf(req, persona_key=persona_key)
    return await decide_legacy(req, persona_key=persona_key)


async def decide_legacy(req: StepRequest, persona_key: str = "lorena") -> StepResponse:
    """Original brain loop (mock / Ollama / vLLM Gemma)."""
    settings = get_settings()
    operator = OperatorService()
    if operator.is_paused():
        return StepResponse(
            action="fail",
            say="Operator paused.",
            reason="operator_paused",
            done=True,
        )
    cached = operator.get_cached_step(req.session_id, req.step)
    if cached:
        return StepResponse.model_validate(cached)
    if _is_ambiguous_step(req):
        resp = _vision_capture_response(req)
        operator.record_step(
            session_id=req.session_id,
            step=req.step,
            action=resp,
            response=resp.model_dump(),
            session_context=req.session_context,
        )
        _record_step(
            req,
            resp,
            latency_ms=0.0,
            guard_triggered=False,
            guard_reason="vision_on_ambiguous",
        )
        return resp

    state = resolve_state(req)
    if _should_use_playbook(req):
        kick = comment_likes_like_hearts(req, state) or comment_likes_kickstart(req, state)
        if kick is not None:
            kick = apply_guards(req, kick)
            operator.record_step(
                session_id=req.session_id,
                step=req.step,
                action=kick,
                response=kick.model_dump(),
                session_context=req.session_context,
            )
            _record_step(
                req,
                kick,
                latency_ms=0.0,
                guard_triggered=False,
                guard_reason="playbook_kickstart",
            )
            return kick

    persona = get_persona(persona_key)
    user = build_step_user_prompt(req)
    shot = (req.screen.screenshot_b64 or "").strip()
    use_vision = bool(shot) and settings.vision_enabled
    if use_vision and _instagram_ui_step(req):
        llm = get_vision_llm()
    elif use_vision:
        llm = get_vision_llm()
    else:
        llm = get_llm()
    images = [shot] if use_vision else []

    started = time.perf_counter()
    try:
        raw = await llm.chat(
            [ChatMessage("system", persona.system_prompt), ChatMessage("user", user, images=images)],
            json_mode=True,
            temperature=settings.temperature,
            max_tokens=768,
        )
    except Exception:
        if use_vision:
            raw = await get_llm().chat(
                [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)],
                json_mode=True,
                temperature=settings.temperature,
                max_tokens=768,
            )
        else:
            raise
    latency_ms = (time.perf_counter() - started) * 1000

    data = parse_step_json(raw)
    if not data.get("action"):
        data = fallback_step_data(req)
    resp_raw = response_from_json(data)
    resp = apply_guards(req, resp_raw)
    allowed, quota_reason = operator.ensure_action_allowed(
        action=resp,
        session_context=req.session_context,
    )
    if not allowed and quota_reason:
        resp = StepResponse(
            action="done",
            say="Daily quota reached.",
            reason=quota_reason,
            done=True,
        )
    guard_triggered, guard_reason = _guard_info(req, resp_raw, resp)
    _record_step(
        req,
        resp,
        latency_ms=latency_ms,
        guard_triggered=guard_triggered,
        guard_reason=guard_reason,
    )
    operator.record_step(
        session_id=req.session_id,
        step=req.step,
        action=resp,
        response=resp.model_dump(),
        session_context=req.session_context,
    )
    return resp
