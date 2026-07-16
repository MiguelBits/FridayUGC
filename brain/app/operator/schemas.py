from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

TaskStatus = Literal["pending", "claimed", "running", "completed", "failed", "cancelled"]
TaskKind = Literal[
    "reels_scroll",
    "reels_comment_likes",
    "feed_engagement",
    "post_reel",
    "post_story",
    "inbox",
    "warmup",
]


class DailyQuota(BaseModel):
    date: str
    likes: int = 0
    story_likes: int = 0
    comment_likes: int = 0
    comments: int = 0
    dms: int = 0
    follows: int = 0
    posts: int = 0
    stories: int = 0
    reels_scrolled: int = 0


class DailyCaps(BaseModel):
    likes: int = 80
    story_likes: int = 15
    comment_likes: int = 100
    comments: int = 15
    dms: int = 8
    follows: int = 5
    posts: int = 1
    stories: int = 3
    reels_scrolled: int = 40


class OperatorStatus(BaseModel):
    enabled: bool = True
    kill_reason: str | None = None
    fsm_state: str = "IDLE"
    daily: DailyQuota = Field(default_factory=DailyQuota)
    caps: DailyCaps = Field(default_factory=DailyCaps)
    pending_tasks: int = 0
    active_session_id: str | None = None


class TaskRecord(BaseModel):
    task_id: str
    kind: TaskKind
    goal: str
    scheduled_at: str
    status: TaskStatus = "pending"
    mode: str = "full"
    session_context: dict[str, Any] = Field(default_factory=dict)
    max_steps: int = 40
    claimed_by: str | None = None
    session_id: str | None = None
    result_summary: str | None = None
    error: str | None = None


class DayPlanRequest(BaseModel):
    timezone: str = "America/New_York"
    mode: str = "full"
    include_post: bool = True
    include_stories: bool = True
    comment_likes_target: int = 100
    reels_target: int = 10
    reels_only: bool = False
    reels_sessions: int = 4


class DayPlanResponse(BaseModel):
    date: str
    tasks: list[TaskRecord]
    strategy_notes: str = ""


class TaskClaimRequest(BaseModel):
    device_id: str
    after: str | None = None


class TaskClaimResponse(BaseModel):
    task: TaskRecord | None = None
    operator: OperatorStatus


class TaskCompleteRequest(BaseModel):
    task_id: str
    session_id: str
    ok: bool
    summary: str = ""
    error: str | None = None
    session_context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class TaskCompleteResponse(BaseModel):
    ok: bool
    operator: OperatorStatus


class CheckpointRequest(BaseModel):
    session_id: str
    task_id: str | None = None
    goal: str
    step: int
    history: list[str] = Field(default_factory=list)
    session_context: dict[str, Any] = Field(default_factory=dict)
    last_action: str | None = None
    last_ok: bool = True


class CheckpointResponse(BaseModel):
    ok: bool
    resume_token: str


class ResumeRequest(BaseModel):
    resume_token: str
    device_id: str


class ResumeResponse(BaseModel):
    checkpoint: CheckpointRequest | None = None
    task: TaskRecord | None = None


class KillRequest(BaseModel):
    reason: str = "manual stop"


class IdempotencyResult(BaseModel):
    hit: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
