from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Channel = Literal["dm", "comment"]
DecisionAction = Literal["reply", "skip", "defer", "needs_approval"]


class IncomingMessage(BaseModel):
    """One DM or comment the phone scraped from Instagram."""

    message_id: str
    thread_id: str = ""
    author: str = Field(..., description="IG handle without @")
    text: str
    channel: Channel = "dm"
    post_id: str = ""
    received_at: Optional[str] = None


class MessageDecision(BaseModel):
    message_id: str
    author: str
    channel: Channel = "dm"
    action: DecisionAction
    reason: str
    draft: Optional[str] = None
    approval_required: bool = False
    replies_today_for_user: int = 0
    cap_per_user_per_day: int = 2


class EvaluateInboxRequest(BaseModel):
    messages: list[IncomingMessage]
    draft_if_reply: bool = True


class EvaluateInboxResponse(BaseModel):
    decisions: list[MessageDecision]
    policy_summary: str
    global_replies_today: int
    global_cap_today: int


class RecordReplyRequest(BaseModel):
    message_id: str
    author: str
    channel: Channel = "dm"
    text_sent: str
    thread_id: str = ""


class RecordReplyResponse(BaseModel):
    ok: bool
    replies_today_for_user: int


class InboxPolicyResponse(BaseModel):
    max_replies_per_user_per_day: int
    max_replies_global_per_day: int
    min_hours_between_same_user: float
    skip_low_effort: bool
    low_effort_reply_probability: float
    comment_max_per_user_per_day: int
