from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

MediaKind = Literal["reel", "photo", "carousel_slide"]
ContentPillar = Literal["gym", "food", "outfit", "lifestyle", "silent", "other"]
PostFormat = Literal["reel", "carousel", "story", "single_photo"]


class GalleryAsset(BaseModel):
    """One piece of media in the cloud gallery (S3 or local dev folder)."""

    id: str
    s3_key: str = ""
    local_path: str = ""
    thumbnail_key: str = ""
    kind: MediaKind = "reel"
    description: str = Field(..., description="Human hint — vision model also sees the actual frame.")
    pillar: ContentPillar = "other"
    duration_s: Optional[float] = None
    tags: list[str] = Field(default_factory=list)
    posted: bool = False
    created_at: Optional[str] = None
    # Filled by vision analysis (brain actually sees the image/frame).
    vision_summary: Optional[str] = None
    vibe: Optional[str] = None
    visual_tags: list[str] = Field(default_factory=list)
    pairing_hints: list[str] = Field(default_factory=list)
    suggested_lane: Optional[str] = None
    suggested_type: Optional[str] = None
    on_screen_text_hint: Optional[str] = None
    identity_ok: bool = True
    vision_analyzed_at: Optional[str] = None


class GalleryManifest(BaseModel):
    account: str = "@itslorenamor"
    assets: list[GalleryAsset] = Field(default_factory=list)
    bio_current: str = ""
    hashtag_bank: list[str] = Field(default_factory=list)


class CommentToReply(BaseModel):
    post_id: str = ""
    comment_id: str = ""
    author: str = ""
    text: str
    context: str = ""


class CurateRequest(BaseModel):
    """Ask Friday to plan a week of UGC from the gallery."""

    days_ahead: int = Field(default=7, ge=1, le=14)
    max_posts_per_day: int = Field(default=2, ge=1, le=4)
    include_bio_update: bool = False
    pending_comments: list[CommentToReply] = Field(default_factory=list)
    notes: Optional[str] = None
    refresh_vision: bool = Field(
        default=True,
        description="Analyze gallery frames with vision model before curating.",
    )


class ScheduledPost(BaseModel):
    asset_ids: list[str]
    format: PostFormat
    lane: str
    type: str
    cta: int
    code: str
    on_screen_text: str = ""
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    scheduled_date: str
    pillar: ContentPillar = "other"
    approval_required: bool = True
    pairing_reason: str = ""


class CarouselGroup(BaseModel):
    group_id: str
    asset_ids: list[str]
    theme: str
    caption: str
    hashtags: list[str] = Field(default_factory=list)


class CommentReplyDraft(BaseModel):
    comment_id: str = ""
    post_id: str = ""
    reply: str
    tone: str = "lorena"


class RetrievalHit(BaseModel):
    """Semantic retrieval match — gallery asset or caption example."""

    id: str
    score: float = Field(ge=0.0, le=1.0)
    pillar: str = ""
    kind: Literal["gallery", "caption"] = "gallery"


class CurateResponse(BaseModel):
    posting_queue: list[ScheduledPost]
    carousel_groups: list[CarouselGroup] = Field(default_factory=list)
    bio_suggestion: Optional[str] = None
    comment_replies: list[CommentReplyDraft] = Field(default_factory=list)
    hashtag_bank: list[str] = Field(default_factory=list)
    strategy_notes: str = ""
    rag_hits: list[RetrievalHit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    comment: CommentToReply
    max_words: int = 18


class ReplyResponse(BaseModel):
    reply: str
    warnings: list[str] = Field(default_factory=list)


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    situation: Optional[str] = None


class GalleryListResponse(BaseModel):
    account: str
    total: int
    unposted: int
    assets: list[GalleryAsset]


class RecordPostRequest(BaseModel):
    asset_ids: list[str]
    item_id: str | None = None
    idempotency_key: str
    format: str = "reel"
    posted_at: str | None = None


class RecordPostResponse(BaseModel):
    ok: bool
    deduplicated: bool = False


class QueueSyncRequest(BaseModel):
    asset_ids: list[str]
    format: PostFormat
    caption: str
    hashtags: list[str] = Field(default_factory=list)
    location: str = ""
    scheduled_at: str
    timezone: str = "America/New_York"


class GallerySyncAsset(BaseModel):
    asset_id: str
    url: str = ""
    kind: str = ""
    local_path: str = ""


class GalleryDueItem(BaseModel):
    item_id: str = ""
    asset_ids: list[str] = Field(default_factory=list)
    format: str = ""
    caption: str = ""
    assets: list[GallerySyncAsset] = Field(default_factory=list)


class GallerySyncResponse(BaseModel):
    due_items: list[GalleryDueItem] = Field(default_factory=list)


class AnalyzeGalleryRequest(BaseModel):
    asset_ids: list[str] = Field(default_factory=list, description="Empty = analyze all.")
    force: bool = False


class VisionAnalysis(BaseModel):
    id: str
    vision_summary: str
    vibe: str
    pillar: ContentPillar = "other"
    visual_tags: list[str] = Field(default_factory=list)
    pairing_hints: list[str] = Field(default_factory=list)
    suggested_lane: Optional[str] = None
    suggested_type: Optional[str] = None
    identity_ok: bool = True
    vision_analyzed_at: Optional[str] = None


class AnalyzeGalleryResponse(BaseModel):
    analyzed: int
    assets: list[VisionAnalysis]
    warnings: list[str] = Field(default_factory=list)
