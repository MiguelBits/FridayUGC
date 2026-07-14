from __future__ import annotations

from typing import Any

from ..agent.actions import StepResponse
from .planner import DayPlanner
from .schemas import (
    CheckpointRequest,
    CheckpointResponse,
    DayPlanRequest,
    DayPlanResponse,
    KillRequest,
    OperatorStatus,
    ResumeRequest,
    ResumeResponse,
    TaskClaimRequest,
    TaskClaimResponse,
    TaskCompleteRequest,
    TaskCompleteResponse,
    TaskRecord,
)
from .store import OperatorStore


class OperatorService:
    def __init__(self, store: OperatorStore | None = None) -> None:
        self.store = store or OperatorStore()
        self.planner = DayPlanner(self.store)

    def status(self) -> OperatorStatus:
        return self.store.status()

    def kill(self, req: KillRequest) -> OperatorStatus:
        self.store.kill(req.reason)
        return self.store.status()

    def resume(self) -> OperatorStatus:
        self.store.resume_operator()
        return self.store.status()

    def day_plan(self, req: DayPlanRequest) -> DayPlanResponse:
        return self.planner.build(req)

    def list_tasks(self, day: str | None = None) -> list[TaskRecord]:
        return self.store.list_tasks(day)

    def claim(self, req: TaskClaimRequest) -> TaskClaimResponse:
        if not self.store.is_enabled():
            return TaskClaimResponse(task=None, operator=self.store.status())
        task = self.store.claim_next_task(req.device_id, req.after)
        return TaskClaimResponse(task=task, operator=self.store.status())

    def complete(self, req: TaskCompleteRequest) -> TaskCompleteResponse:
        if req.idempotency_key:
            cached = self.store.get_idempotent(req.idempotency_key)
            if cached:
                return TaskCompleteResponse(ok=True, operator=self.store.status())
        self.store.complete_task(
            req.task_id,
            ok=req.ok,
            summary=req.summary,
            error=req.error,
            session_context=req.session_context,
        )
        if req.idempotency_key:
            self.store.put_idempotent(
                req.idempotency_key,
                {"task_id": req.task_id, "ok": req.ok, "summary": req.summary},
            )
        return TaskCompleteResponse(ok=True, operator=self.store.status())

    def checkpoint(self, req: CheckpointRequest) -> CheckpointResponse:
        token = self.store.save_checkpoint(req)
        return CheckpointResponse(ok=True, resume_token=token)

    def resume_session(self, req: ResumeRequest) -> ResumeResponse:
        checkpoint = self.store.load_checkpoint(req.resume_token)
        task = None
        if checkpoint and checkpoint.session_id:
            for t in self.store.list_tasks():
                if t.session_id == checkpoint.session_id:
                    task = t
                    break
        return ResumeResponse(checkpoint=checkpoint, task=task)

    def is_paused(self) -> bool:
        return not self.store.is_enabled()

    def get_cached_step(self, session_id: str, step: int) -> dict[str, Any] | None:
        return self.store.get_step_response(session_id, step)

    def ensure_action_allowed(
        self,
        *,
        action: StepResponse,
        session_context: dict[str, Any],
    ) -> tuple[bool, str | None]:
        if not self.store.is_enabled():
            return False, "operator_paused"
        daily = self.store.get_daily()
        caps = self.store.get_caps()
        blocked = self._quota_block(action.action, daily, caps)
        if blocked:
            return False, blocked
        return True, None

    def record_step(
        self,
        *,
        session_id: str,
        step: int,
        action: StepResponse,
        response: dict[str, Any],
        session_context: dict[str, Any],
    ) -> None:
        self.store.put_step_response(session_id, step, response)
        if action.action not in {"wait", "done", "fail", "scroll", "swipe", "navigate", "press", "open_app"}:
            self.store.apply_engagement(action.action, session_context)

    @staticmethod
    def _quota_block(action: str, daily, caps) -> str | None:
        checks = {
            "like": (daily.likes, caps.likes, "daily_like_cap"),
            "like_story": (daily.story_likes, caps.story_likes, "daily_story_like_cap"),
            "like_comment": (daily.comment_likes, caps.comment_likes, "daily_comment_like_cap"),
            "comment": (daily.comments, caps.comments, "daily_comment_cap"),
            "dm": (daily.dms, caps.dms, "daily_dm_cap"),
            "follow": (daily.follows, caps.follows, "daily_follow_cap"),
            "post": (daily.posts, caps.posts, "daily_post_cap"),
            "story": (daily.stories, caps.stories, "daily_story_cap"),
        }
        if action not in checks:
            return None
        used, cap, code = checks[action]
        if used >= cap:
            return code
        return None
