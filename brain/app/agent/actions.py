from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ActionName = Literal[
    "tap",
    "scroll",
    "swipe",
    "type",
    "press",
    "open_app",
    "wait",
    "navigate",
    "post",
    "comment",
    "dm",
    "like",
    "like_story",
    "like_comment",
    "view_story",
    "follow",
    "unfollow",
    "save",
    "done",
    "fail",
]


class ScreenElement(BaseModel):
    id: int
    role: str = ""
    text: str = ""
    scrollable: bool = False
    editable: bool = False
    clickable: bool = False
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


class Screen(BaseModel):
    app: str = ""
    activity: str = ""
    elements: list[ScreenElement] = []
    screenshot_b64: Optional[str] = None


class ScreenState(BaseModel):
    """Structured perception from phone — general mobile vocabulary, Instagram today."""

    app_package: str = ""
    activity_class: str = ""
    screen_type: str = "unknown"
    selected_tab: str = "unknown"
    confidence: float = 0.0
    element_count: int = 0
    signals: list[str] = Field(default_factory=list)
    needs_vision: bool = False


class LastResult(BaseModel):
    action: Optional[str] = None
    ok: bool = True
    error: Optional[str] = None
    verified: Optional[str] = None
    change_score: float = 0.0


OperatingMode = Literal["read_only", "full"]


class StepRequest(BaseModel):
    session_id: str
    goal: str
    step: int = 0
    screen: Screen
    last_result: Optional[LastResult] = None
    history: list[str] = []
    mode: OperatingMode = "read_only"
    device_id: str = ""
    screen_fingerprint: str = ""
    screen_state: ScreenState | None = None
    ig_version: str = ""
    session_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Engagement budgets: likes_used, likes_max, phase, etc.",
    )


class StepResponse(BaseModel):
    action: ActionName
    params: dict[str, Any] = Field(default_factory=dict)
    say: Optional[str] = None
    reason: str = ""
    done: bool = False
    needs_screenshot: bool = False
    approval_required: bool = False
