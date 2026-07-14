from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Lane = Literal["A", "B", "C", "D", "E"]
ContentType = Literal[
    "product skin",
    "outfit try-on",
    "workout exercise",
    "food tutorial",
    "others",
    "fashion-only",
    "silent",
    "camera study",
]
CTA = Literal[1, 2, 3]


# --- /ugc/plan ---
class PlanRequest(BaseModel):
    ref_description: str = Field(..., description="What the reference photo/video shows.")
    type_hint: Optional[ContentType] = None
    lane_hint: Optional[Lane] = None
    notes: Optional[str] = None


class PlanResponse(BaseModel):
    lane: Lane
    type: ContentType
    cta: CTA
    code: str
    on_screen_text: str
    hook: str
    caption: str
    warnings: list[str] = []


# --- /ugc/caption ---
class CaptionRequest(BaseModel):
    context: str = Field(..., description="What the reel/post is about.")
    cta: CTA = 1
    max_words: int = 22


class CaptionResponse(BaseModel):
    caption: str
    rag_examples: list[str] = Field(
        default_factory=list,
        description="Past posted captions retrieved as style references.",
    )
    warnings: list[str] = []


# --- /ugc/prompt (generation prompt) ---
class GenPromptRequest(BaseModel):
    ref_description: str
    lane: Lane = "A"
    type: ContentType = "silent"
    cta: CTA = 1
    duration_s: int = 8
    setting: Optional[str] = None
    style: Literal["ugc_block", "timed_beat"] = "ugc_block"


class GenPromptResponse(BaseModel):
    prompt: str
    code: str
    warnings: list[str] = []


# --- /voice/reply ---
class VoiceRequest(BaseModel):
    user_text: str
    situation: Optional[str] = None


class VoiceResponse(BaseModel):
    reply: str
