"""Resolve internal motor plans to atomic actions with inline vision grounding."""

from __future__ import annotations

from .actions import GroundRequest, ObserveBundle, StepResponse
from .flows.defs import comments_icon_xy
from .flows.memory import next_comments_y_frac
from .grounding import ground_target
from .routines import MotorPlan


def _teach_coord(device_id: str, ui_key: str) -> tuple[int, int] | None:
    """Prefer human-taught open_comments coords (TeachStore) when n_ok >= 3."""
    if not device_id or ui_key != "comments_icon":
        return None
    try:
        from adb.teach.store import TeachStore

        return TeachStore().get_skill_coord("open_comments", device_id)
    except Exception:
        try:
            from brain.adb.teach.store import TeachStore

            return TeachStore().get_skill_coord("open_comments", device_id)
        except Exception:
            return None


def _memory_coord(device_id: str, ui_key: str) -> tuple[int, int] | None:
    if not device_id or not ui_key:
        return None
    taught = _teach_coord(device_id, ui_key)
    if taught:
        return taught
    try:
        from ..learning.store import LearningStore

        for entry in LearningStore().get_memory(device_id):
            if entry.ui_key != ui_key or entry.x <= 0 or entry.y <= 0:
                continue
            if entry.success_count > entry.fail_count:
                return entry.x, entry.y
    except Exception:
        return None
    return None


def _deterministic_comments(plan: MotorPlan, observe: ObserveBundle, ctx: dict | None) -> StepResponse:
    w = observe.screen_width or 1080
    h = observe.screen_height or 2400
    y_frac = next_comments_y_frac(ctx or {}, screen_width=w, screen_height=h)
    xi, yi = comments_icon_xy(w, h, y_frac=y_frac)
    return StepResponse(
        action=plan.action,  # type: ignore[arg-type]
        params={"x": xi, "y": yi, "ui_key": plan.anchor, "y_frac": y_frac},
        say=plan.say or "Open comments (deterministic).",
        reason=f"{plan.reason} — deterministic comments_icon y_frac={y_frac:.3f}",
    )


def _motor_fallback(plan: MotorPlan, observe: ObserveBundle | None = None, ctx: dict | None = None) -> StepResponse | None:
    if plan.anchor == "nav_reels":
        return StepResponse(
            action="navigate",
            params={"tab": "reels"},
            say=plan.say or "Opening Reels.",
            reason=f"{plan.reason} — navigate fallback",
        )
    if plan.anchor == "comments_icon" and observe is not None:
        return _deterministic_comments(plan, observe, ctx)
    return None


async def resolve_plan(
    plan: MotorPlan,
    observe: ObserveBundle,
    device_id: str,
    screen_type: str = "",
    session_context: dict | None = None,
) -> tuple[StepResponse, bool]:
    """Return StepResponse ready for phone executor; grounded=True if vision used.

    Resolution order for comments_icon: teach → memory → vision → deterministic %.
    """
    if plan.kind != "ground_tap":
        from .routines import plan_to_step_response

        return plan_to_step_response(plan), False

    ctx = session_context or {}
    mem = _memory_coord(device_id, plan.anchor)
    if mem and plan.anchor == "comments_icon":
        xi, yi = mem
        taught = _teach_coord(device_id, plan.anchor)
        src = "teach skill" if taught and taught == mem else "device memory (success > fail)"
        return (
            StepResponse(
                action=plan.action,  # type: ignore[arg-type]
                params={"x": xi, "y": yi, "ui_key": plan.anchor},
                say=plan.say,
                reason=f"{plan.anchor} from {src}",
            ),
            False,
        )

    shot = (observe.screen.screenshot_b64 or "").strip()
    if not shot:
        if mem:
            xi, yi = mem
            return (
                StepResponse(
                    action=plan.action,  # type: ignore[arg-type]
                    params={"x": xi, "y": yi, "ui_key": plan.anchor},
                    say=plan.say,
                    reason=f"{plan.anchor} from device memory (no screenshot)",
                ),
                False,
            )
        fallback = _motor_fallback(plan, observe, ctx)
        if fallback:
            return fallback, False
        return (
            StepResponse(
                action="wait",
                params={"ms": 400},
                say=plan.say or "Need screenshot for vision.",
                reason=f"{plan.anchor} needs screenshot",
                needs_screenshot=True,
            ),
            False,
        )

    req = GroundRequest(
        anchor=plan.anchor,
        screenshot_b64=shot,
        screen_width=observe.screen_width or 1080,
        screen_height=observe.screen_height or 2400,
        screen_type=screen_type,
        elements=observe.screen.elements,
        row_index=plan.row_index,
        som_marks=observe.som_marks,
        use_som=len(observe.som_marks) > 0,
        device_id=device_id,
    )
    ground = await ground_target(req)
    if ground.needs_screenshot or not ground.params:
        if mem:
            xi, yi = mem
            return (
                StepResponse(
                    action=plan.action,  # type: ignore[arg-type]
                    params={"x": xi, "y": yi, "ui_key": plan.anchor},
                    say=plan.say,
                    reason=ground.reason or f"{plan.anchor} from device memory",
                ),
                False,
            )
        fallback = _motor_fallback(plan, observe, ctx)
        if fallback:
            return fallback, False
        return (
            StepResponse(
                action="wait",
                params={"ms": 800},
                say=plan.say,
                reason=ground.reason or f"{plan.anchor} ground failed — retrying",
                needs_screenshot=False,
            ),
            False,
        )

    action = ground.action if ground.action in {"tap", "like_comment"} else plan.action
    params = dict(ground.params)
    params["ui_key"] = plan.anchor
    return (
        StepResponse(
            action=action,  # type: ignore[arg-type]
            params=params,
            say=plan.say,
            reason=ground.reason or plan.reason,
        ),
        True,
    )


async def resolve_intent_step_async(
    resp: StepResponse,
    observe: ObserveBundle,
    device_id: str,
    screen_type: str = "",
    row_index: int = 0,
) -> tuple[StepResponse, bool]:
    if resp.action != "intent":
        return resp, False
    name = str((resp.params or {}).get("name", "")).lower()
    anchor_map = {
        "enter_reels": ("nav_reels", "tap"),
        "open_comments": ("comments_icon", "tap"),
        "engage_comments": ("comment_heart", "like_comment"),
    }
    if name not in anchor_map:
        if name == "next_reel":
            return (
                StepResponse(
                    action="swipe",
                    params={"direction": "up", "zone": "reels_rail"},
                    say=resp.say,
                    reason=resp.reason,
                ),
                False,
            )
        if name == "go_back":
            return (
                StepResponse(action="press", params={"key": "back"}, say=resp.say, reason=resp.reason),
                False,
            )
        return resp, False
    anchor, action = anchor_map[name]
    plan = MotorPlan(
        kind="ground_tap",
        anchor=anchor,
        action=action,
        say=resp.say or "",
        reason=resp.reason or f"resolve intent {name}",
        row_index=row_index,
    )
    return await resolve_plan(plan, observe, device_id, screen_type)
