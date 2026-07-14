from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SessionStatus = Literal["active", "done", "failed"]


class StepTrace(BaseModel):
    step: int
    goal: str
    foreground_app: str = ""
    action: str
    approval_required: bool = False
    guard_triggered: bool = False
    guard_reason: str = ""
    latency_ms: float = 0.0
    provider: str = ""
    at: str


class SessionRun(BaseModel):
    session_id: str
    goal: str = ""
    status: SessionStatus = "active"
    started_at: str
    updated_at: str
    steps: list[StepTrace] = Field(default_factory=list)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def guard_interventions(self) -> int:
        return sum(1 for s in self.steps if s.guard_triggered)

    @property
    def avg_latency_ms(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.latency_ms for s in self.steps) / len(self.steps)


class RunMetrics(BaseModel):
    sessions_total: int
    sessions_done: int
    sessions_failed: int
    sessions_active: int
    steps_total: int
    guard_interventions: int
    avg_latency_ms: float
    completion_rate: float
