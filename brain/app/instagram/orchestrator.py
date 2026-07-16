"""Operator daemon — claim tasks, run Instagram API workers, complete."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from ..config import get_settings
from ..operator.schemas import DayPlanRequest, TaskCompleteRequest, TaskRecord
from ..operator.service import OperatorService
from .budget import EngagementBudget
from .engagement import reels_comment_likes_session

logger = logging.getLogger(__name__)

# Only these kinds run until other routines are implemented.
ENABLED_KINDS = frozenset({"reels_comment_likes", "reels_scroll"})


class InstagramOrchestrator:
    def __init__(self, operator: OperatorService | None = None) -> None:
        self.operator = operator or OperatorService()
        self.settings = get_settings()

    @property
    def worker_id(self) -> str:
        return self.settings.ig_worker_id or "instagram-api"

    def status(self) -> dict[str, Any]:
        op = self.operator.status()
        budget = EngagementBudget(self.operator.store).snapshot()
        return {
            "worker_id": self.worker_id,
            "operator_enabled": op.enabled,
            "fsm_state": op.fsm_state,
            "pending_tasks": op.pending_tasks,
            "daily_comment_likes": f"{budget.comment_likes_used}/{budget.comment_likes_cap}",
            "daily_reels": f"{budget.reels_scrolled}/{budget.reels_scrolled_cap}",
            "enabled_kinds": sorted(ENABLED_KINDS),
        }

    def plan_reels_day(self, *, mode: str = "full", sessions: int = 4) -> dict[str, Any]:
        """Create today’s plan with only reels_comment_likes sessions."""
        req = DayPlanRequest(
            mode=mode,
            include_post=False,
            include_stories=False,
            comment_likes_target=self.settings.ugc_comment_likes_max,
            reels_target=self.settings.ugc_reels_max,
            reels_only=True,
            reels_sessions=sessions,
        )
        resp = self.operator.day_plan(req)
        return {
            "date": resp.date,
            "tasks": len(resp.tasks),
            "strategy_notes": resp.strategy_notes,
        }

    def _execute_task(self, task: TaskRecord) -> dict[str, Any]:
        ctx = dict(task.session_context or {})
        read_only = task.mode == "read_only" or self.settings.ig_read_only

        if task.kind not in ENABLED_KINDS:
            return {
                "ok": True,
                "skipped": True,
                "reason": f"kind {task.kind!r} not enabled yet",
            }

        reels_max = int(ctx.get("reels_target") or ctx.get("reels_max") or self.settings.ugc_reels_max)
        per_reel = ctx.get("comment_likes_per_reel")
        if per_reel is not None:
            per_reel = int(per_reel)

        if task.kind == "reels_scroll":
            reels_max = min(reels_max, 5)

        result = reels_comment_likes_session(
            reels_max=reels_max,
            comment_likes_per_reel=per_reel,
            read_only=read_only,
        )

        ctx["comment_likes_done"] = int(ctx.get("comment_likes_done", 0)) + result.get("comment_likes", 0)
        ctx["reels_scrolled"] = int(ctx.get("reels_scrolled", 0)) + result.get("reels_processed", 0)
        ctx["phase"] = "reels_comment_likes"
        result["session_context"] = ctx
        result["ok"] = result.get("ok", True) and not result.get("error")
        return result

    def run_task(self, task: TaskRecord) -> dict[str, Any]:
        logger.info("Executing task %s kind=%s mode=%s", task.task_id[:8], task.kind, task.mode)
        result = self._execute_task(task)
        skipped = bool(result.get("skipped"))
        ok = bool(result.get("ok", True)) if skipped else bool(result.get("ok")) and not result.get("error")
        summary = (
            f"reels={result.get('reels_processed', 0)} "
            f"comment_likes={result.get('comment_likes', 0)}"
        )
        if result.get("stopped"):
            summary += f" stopped={result['stopped']}"
        if skipped:
            ok = True
            summary = result.get("reason", "skipped")

        self.operator.complete(
            TaskCompleteRequest(
                task_id=task.task_id,
                session_id=task.session_id or str(uuid.uuid4()),
                ok=ok,
                summary=summary,
                error=result.get("error"),
                session_context=result.get("session_context", {}),
                idempotency_key=f"ig-task-{task.task_id}",
            )
        )
        return result

    def claim_and_run(self) -> dict[str, Any] | None:
        if not self.operator.store.is_enabled():
            logger.info("Operator paused — nothing to claim")
            return None

        from ..operator.schemas import TaskClaimRequest

        claim = self.operator.claim(TaskClaimRequest(device_id=self.worker_id))
        task = claim.task
        if not task:
            return None
        return self.run_task(task)

    def run_reels_now(
        self,
        *,
        reels_max: int | None = None,
        comment_likes_per_reel: int | None = None,
        read_only: bool | None = None,
    ) -> dict[str, Any]:
        """One-shot reels + comment likes (no operator task required)."""
        settings = get_settings()
        read_only = settings.ig_read_only if read_only is None else read_only
        return reels_comment_likes_session(
            reels_max=reels_max,
            comment_likes_per_reel=comment_likes_per_reel,
            read_only=read_only,
        )

    def daemon(self, *, poll_seconds: float | None = None) -> None:
        """Poll operator queue and run reels tasks until killed."""
        interval = poll_seconds if poll_seconds is not None else self.settings.ig_poll_seconds
        logger.info("Instagram daemon started worker=%s poll=%ss kinds=%s", self.worker_id, interval, ENABLED_KINDS)
        while self.operator.store.is_enabled():
            try:
                result = self.claim_and_run()
                if result is None:
                    time.sleep(interval)
                    continue
                logger.info("Task finished: %s", result)
            except KeyboardInterrupt:
                logger.info("Daemon stopped")
                break
            except Exception:
                logger.exception("Daemon loop error")
                time.sleep(min(interval * 2, 60))
