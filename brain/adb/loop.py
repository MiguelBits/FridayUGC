"""Observe → tick → execute → report loop (thin ADB client)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from app.agent.actions import ObserveBundle, TickLastResult, TickRequest, TickResponse
from app.learning.schemas import VerifiedStepRecord
from app.ugc.operator import RoutineKind, RoutineRequest

from .client import BrainClient
from .device import device_id_from_serial, resolve_serial, session_prep
from .executor import ExecutorResult, execute, settle_ms
from .learning import step_record, trajectory_batch
from .observe import build_observe

logger = logging.getLogger(__name__)

OperatingMode = Literal["read_only", "full"]
MAX_CONSECUTIVE_FAILURES = 8
RECOVERY_AT_FAILURES = 5

APPROVAL_ACTIONS = frozenset({"post", "comment", "dm", "follow"})


@dataclass
class LoopConfig:
    brain_url: str
    token: str
    goal: str
    mode: OperatingMode = "read_only"
    max_steps: int = 40
    serial: Optional[str] = None
    autonomous: bool = False
    routine: Optional[RoutineKind] = None
    reels_max: Optional[int] = None
    comment_likes_per_reel: Optional[int] = None
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class LoopState:
    step: int = 0
    consecutive_failures: int = 0
    recovery_used: bool = False
    session_context: dict[str, Any] = field(default_factory=dict)
    trajectory_steps: list[VerifiedStepRecord] = field(default_factory=list)
    last_result: Optional[TickLastResult] = None


def _prompt_approval(action: str, params: dict[str, Any]) -> bool:
    try:
        answer = input(f"Approve {action} {params}? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in {"y", "yes"}


async def _tick_with_screenshot(
    client: BrainClient,
    request: TickRequest,
    *,
    serial: Optional[str],
) -> TickResponse:
    response = await client.tick(request)
    if not response.needs_screenshot:
        return response
    observe = build_observe(serial=serial, include_screenshot=True, ig_only_screenshot=False)
    request.observe = observe
    return await client.tick(request)


async def run_loop(config: LoopConfig) -> LoopState:
    serial = resolve_serial(config.serial)
    device_id = device_id_from_serial(serial)
    session_prep(serial=serial)

    client = BrainClient(config.brain_url, config.token)
    await client.health()

    goal = config.goal
    session_context: dict[str, Any] = {}
    if config.routine:
        routine_resp = await client.routine(
            RoutineRequest(routine=config.routine, mode=config.mode)
        )
        goal = routine_resp.goal
        session_context = routine_resp.session_context.model_dump()
        logger.info("Routine %s goal: %s", config.routine, goal)

    if config.reels_max is not None:
        session_context["reels_max"] = config.reels_max
    if config.comment_likes_per_reel is not None:
        session_context["comment_likes_per_reel_fixed"] = config.comment_likes_per_reel
        session_context["comment_likes_per_reel"] = config.comment_likes_per_reel
        session_context["comment_likes_min_per_reel"] = config.comment_likes_per_reel
        session_context["comment_likes_max_per_reel"] = config.comment_likes_per_reel

    try:
        mem = await client.get_memory(device_id)
        if mem.entries:
            logger.info("Hydrated %d device memory entries", len(mem.entries))
    except Exception as exc:
        logger.warning("Could not hydrate device memory: %s", exc)

    state = LoopState(session_context=session_context)

    while state.step < config.max_steps:
        observe = build_observe(serial=serial, include_screenshot=True)
        request = TickRequest(
            session_id=config.session_id,
            device_id=device_id,
            goal=goal,
            step=state.step,
            observe=observe,
            last_result=state.last_result,
            mode=config.mode,
            session_context=state.session_context,
        )
        try:
            response = await _tick_with_screenshot(client, request, serial=serial)
        except Exception as exc:
            state.consecutive_failures += 1
            logger.error("Tick failed: %s", exc)
            if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                logger.error("Circuit breaker: %d consecutive failures", state.consecutive_failures)
                break
            if state.consecutive_failures >= RECOVERY_AT_FAILURES and not state.recovery_used:
                logger.warning("Recovery: press back")
                execute(
                    "press",
                    {"key": "back"},
                    screen_width=observe.screen_width,
                    screen_height=observe.screen_height,
                    serial=serial,
                )
                time.sleep(1.0)
                state.recovery_used = True
                state.consecutive_failures = 0
            continue

        if response.say:
            logger.info("Brain says: %s", response.say)

        state.session_context = response.session_context or state.session_context

        if response.action in {"done", "fail"}:
            logger.info("Loop ended: %s — %s", response.action, response.reason)
            break

        if response.approval_required and response.action in APPROVAL_ACTIONS:
            if not config.autonomous and not _prompt_approval(response.action, response.params):
                logger.info("User declined %s", response.action)
                break

        logger.info(
            "Executing step=%s action=%s params=%s size=%sx%s",
            state.step,
            response.action,
            response.params,
            observe.screen_width,
            observe.screen_height,
        )

        before_observe = observe
        result = execute(
            response.action,
            response.params,
            screen_width=observe.screen_width,
            screen_height=observe.screen_height,
            serial=serial,
            mode=config.mode,
        )

        if not result.ok:
            state.consecutive_failures += 1
            state.last_result = TickLastResult(
                action=response.action,
                executor_ok=False,
                error=result.error,
                ui_key=result.ui_key or str(response.params.get("ui_key") or ""),
                params=response.params,
                before_observe=before_observe,
            )
            logger.warning("Executor failed: %s", result.error)
            if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                break
            state.step += 1
            continue

        time.sleep(settle_ms(response.action) / 1000.0)
        after_observe = build_observe(serial=serial, include_screenshot=True)

        state.last_result = TickLastResult(
            action=response.action,
            executor_ok=True,
            ui_key=result.ui_key or str(response.params.get("ui_key") or ""),
            params=response.params,
            before_observe=before_observe,
            after_observe=after_observe,
            verified=response.reason or None,
        )

        record = step_record(
            session_id=config.session_id,
            device_id=device_id,
            step=state.step,
            goal=goal,
            last_result=state.last_result,
            verified="unknown",
            ig_version=observe.ig_version,
        )
        state.trajectory_steps.append(record)
        try:
            await client.post_trajectory(trajectory_batch(device_id, [record]))
        except Exception as exc:
            logger.warning("Trajectory sync failed: %s", exc)

        state.consecutive_failures = 0
        state.recovery_used = False
        state.step += 1

    if state.trajectory_steps:
        try:
            await client.post_trajectory(trajectory_batch(device_id, state.trajectory_steps))
        except Exception as exc:
            logger.warning("Final trajectory sync failed: %s", exc)

    return state


def run_loop_sync(config: LoopConfig) -> LoopState:
    return asyncio.run(run_loop(config))
