from __future__ import annotations

from .evaluator import LearningEvaluator
from .events import event_logger
from .schemas import (
    DeviceMemoryResponse,
    DeviceMemorySyncRequest,
    EvalReport,
    LearningMetrics,
    NovelPlanRecord,
    TrajectoryBatchRequest,
    TrajectoryBatchResponse,
    VerifiedStepRecord,
)
from .store import LearningStore


class LearningService:
    def __init__(self, store: LearningStore | None = None) -> None:
        self.store = store or LearningStore()
        self.evaluator = LearningEvaluator(self.store)

    def record_trajectory(self, req: TrajectoryBatchRequest) -> TrajectoryBatchResponse:
        accepted, failures = self.store.record_steps(req.steps)
        novel = self.store.record_novel_plans(req.steps)
        for plan in novel:
            event_logger.novel_plan(plan.device_id, plan.signature, plan.goal)
        event_logger.trajectory_batch(req.device_id, accepted, failures)
        return TrajectoryBatchResponse(accepted=accepted, failures_recorded=failures)

    def sync_memory(self, req: DeviceMemorySyncRequest) -> DeviceMemoryResponse:
        self.store.sync_memory(req.device_id, req.entries)
        return DeviceMemoryResponse(device_id=req.device_id, entries=self.store.get_memory(req.device_id))

    def get_memory(self, device_id: str) -> DeviceMemoryResponse:
        return DeviceMemoryResponse(device_id=device_id, entries=self.store.get_memory(device_id))

    def memory_hints(self, device_id: str) -> str:
        return self.store.memory_hints_for_prompt(device_id)

    def run_eval(self, limit: int = 50) -> EvalReport:
        return self.evaluator.run(limit=limit)

    def latest_eval(self) -> EvalReport | None:
        return self.store.latest_eval_report()

    def metrics(self) -> LearningMetrics:
        return self.store.metrics()

    def list_novel_plans(self, device_id: str | None = None, limit: int = 20) -> list[NovelPlanRecord]:
        return self.store.list_novel_plans(device_id=device_id, limit=limit)

    def novel_plan_hints(self, device_id: str, limit: int = 5) -> str:
        return self.store.novel_plan_hints(device_id, limit=limit)
