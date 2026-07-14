from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VerificationStatus = Literal["verified", "unverified", "failed", "unknown"]


class VerifiedStepRecord(BaseModel):
    session_id: str
    device_id: str
    step: int
    goal: str
    action: str
    executor_ok: bool = True
    verified: VerificationStatus = "unknown"
    change_score: float = 0.0
    screen_fp_before: str = ""
    screen_fp_after: str = ""
    foreground_app_before: str = ""
    foreground_app_after: str = ""
    element_count_before: int = 0
    element_count_after: int = 0
    error: str | None = None
    ig_version: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    screenshot_path: str | None = None


class TrajectoryBatchRequest(BaseModel):
    device_id: str
    steps: list[VerifiedStepRecord]


class TrajectoryBatchResponse(BaseModel):
    accepted: int
    failures_recorded: int


class DeviceMemoryEntry(BaseModel):
    device_id: str
    ui_key: str
    x: int = 0
    y: int = 0
    resource_hint: str = ""
    success_count: int = 0
    fail_count: int = 0
    last_verified_at: str = ""
    ig_version: str = ""


class DeviceMemorySyncRequest(BaseModel):
    device_id: str
    entries: list[DeviceMemoryEntry]


class DeviceMemoryResponse(BaseModel):
    device_id: str
    entries: list[DeviceMemoryEntry] = Field(default_factory=list)


class LearningMetrics(BaseModel):
    trajectories_total: int = 0
    verified_steps: int = 0
    failed_steps: int = 0
    verification_rate: float = 0.0
    memory_entries: int = 0
    last_eval_at: str | None = None
    last_eval_pass_rate: float | None = None


class EvalFailureCase(BaseModel):
    session_id: str
    step: int
    action: str
    goal: str
    screen_fp_before: str
    reason: str


class EvalReport(BaseModel):
    ran_at: str
    cases_reviewed: int
    would_fix: int
    pass_rate: float
    failures: list[EvalFailureCase] = Field(default_factory=list)
    notes: str = ""


class NovelPlanRecord(BaseModel):
    device_id: str
    goal: str
    signature: str
    action_sequence: list[str] = Field(default_factory=list)
    step_count: int = 0
    created_at: str = ""
