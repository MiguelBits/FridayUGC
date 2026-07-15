"""Trajectory and device memory sync helpers."""

from __future__ import annotations

from typing import Any, Optional

from app.agent.actions import ObserveBundle, Screen, TickLastResult
from app.learning.schemas import TrajectoryBatchRequest, VerifiedStepRecord

from .observe import screen_fingerprint


def step_record(
    *,
    session_id: str,
    device_id: str,
    step: int,
    goal: str,
    last_result: TickLastResult,
    verified: str = "unknown",
    ig_version: str = "",
) -> VerifiedStepRecord:
    before = last_result.before_observe or ObserveBundle(screen=Screen())
    after = last_result.after_observe or before
    return VerifiedStepRecord(
        session_id=session_id,
        device_id=device_id,
        step=step,
        goal=goal,
        action=last_result.action,
        executor_ok=last_result.executor_ok,
        verified=verified if verified in {"verified", "unverified", "failed", "unknown"} else "unknown",  # type: ignore[arg-type]
        change_score=last_result.change_score,
        screen_fp_before=screen_fingerprint(before),
        screen_fp_after=screen_fingerprint(after),
        foreground_app_before=before.screen.app,
        foreground_app_after=after.screen.app,
        element_count_before=len(before.screen.elements),
        element_count_after=len(after.screen.elements),
        error=last_result.error,
        ig_version=ig_version or before.ig_version,
        params=last_result.params,
        anchor=last_result.ui_key,
        screenshot_b64=after.screen.screenshot_b64,
    )


def trajectory_batch(device_id: str, steps: list[VerifiedStepRecord]) -> TrajectoryBatchRequest:
    return TrajectoryBatchRequest(device_id=device_id, steps=steps)


def memory_entries_from_response(entries: list[Any]) -> list[dict[str, Any]]:
    return [e.model_dump() if hasattr(e, "model_dump") else dict(e) for e in entries]
