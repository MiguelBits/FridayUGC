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
    "intent",
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


class SomMark(BaseModel):
    mark_id: int
    x: int = 0
    y: int = 0
    text: str = ""
    element_id: int = -1


class GroundRequest(BaseModel):
    """Phone → brain: find tap target on screenshot (Gemma 3 vision, local)."""

    anchor: str
    screenshot_b64: str
    screen_width: int = 0
    screen_height: int = 0
    screen_type: str = ""
    elements: list[ScreenElement] = Field(default_factory=list)
    row_index: int = 0
    som_marks: list[SomMark] = Field(default_factory=list)
    use_som: bool = True
    device_id: str = ""


class GroundResponse(BaseModel):
    action: str = "tap"
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""
    needs_screenshot: bool = False


# --- Tick v2: thin-client loop (phone = eyes + hands, brain = operator) ---


class ObserveBundle(BaseModel):
    """Current screen snapshot from phone."""

    screen: Screen
    som_marks: list[SomMark] = Field(default_factory=list)
    screen_width: int = 0
    screen_height: int = 0
    ig_version: str = ""


class TickLastResult(BaseModel):
    """Outcome of the previous executed motor action."""

    action: str = ""
    executor_ok: bool = True
    error: Optional[str] = None
    ui_key: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    before_observe: Optional[ObserveBundle] = None
    after_observe: Optional[ObserveBundle] = None
    verified: Optional[str] = None
    change_score: float = 0.0


class TickRequest(BaseModel):
    session_id: str
    device_id: str = ""
    goal: str
    step: int = 0
    observe: ObserveBundle
    last_result: Optional[TickLastResult] = None
    mode: OperatingMode = "read_only"
    session_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional seed; brain SessionStore is authoritative after tick 0",
    )


class TickResponse(BaseModel):
    action: ActionName
    params: dict[str, Any] = Field(default_factory=dict)
    say: Optional[str] = None
    reason: str = ""
    done: bool = False
    needs_screenshot: bool = False
    approval_required: bool = False
    session_context: dict[str, Any] = Field(default_factory=dict)
    grounded: bool = False
