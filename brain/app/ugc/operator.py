from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..config import get_settings

RoutineKind = Literal[
    "full_session",
    "reels_scroll",
    "reels_comment_likes",
    "stories",
    "feed_engagement",
    "inbox",
    "comments",
    "post",
]

_PLAYBOOK = (Path(__file__).resolve().parent.parent / "agent" / "ugc_operator_prompt.md").read_text(
    encoding="utf-8"
)


class SessionBudget(BaseModel):
    """Per-session engagement caps — phone increments, brain enforces."""

    likes_used: int = 0
    likes_max: int = 25
    story_likes_used: int = 0
    story_likes_max: int = 12
    reels_scrolled: int = 0
    reels_max: int = 35
    comments_used: int = 0
    comments_max: int = 8
    comment_likes_used: int = 0
    comment_likes_max: int = 50
    comment_likes_per_reel: int = 5
    dms_used: int = 0
    dms_max: int = 10
    follows_used: int = 0
    follows_max: int = 3
    saves_used: int = 0
    saves_max: int = 5
    phase: str = "reels"


class RoutineRequest(BaseModel):
    routine: RoutineKind = "full_session"
    duration_minutes: int = Field(default=25, ge=5, le=120)
    mode: Literal["read_only", "full"] = "full"
    notes: str | None = None


class RoutineResponse(BaseModel):
    goal: str
    session_context: SessionBudget
    checklist: list[str]
    playbook_excerpt: str = ""


_ROUTINE_GOALS: dict[RoutineKind, str] = {
    "full_session": (
        "Full UGC operator session on @itslorenamor: "
        "(1) Reels — scroll and like niche gym/outfit/food reels within budget. "
        "(2) Stories — watch and like_story a few creator stories. "
        "(3) Feed — scroll home, like a few posts. "
        "(4) Activity/inbox — check notifications; reply to DMs selectively (inbox policy). "
        "(5) Reply to comments on our posts in Lorena voice. "
        "Respect SESSION_BUDGET; move to next phase when a cap is hit. Human pacing always."
    ),
    "reels_scroll": (
        "Open Instagram Reels and scroll {duration} minutes. "
        "Like reels that match gym, meal prep, outfit try-on, or Miami aesthetic — stay in budget."
    ),
    "reels_comment_likes": (
        "Open Instagram Reels tab. Process exactly 10 reels. "
        "For EACH reel: (1) tap the comments icon to open the comments sheet, "
        "(2) like exactly 5 comments using like_comment on comment heart buttons — "
        "do NOT post new comments, (3) press back to return to the reel, "
        "(4) swipe up to the next reel. "
        "Repeat until 10 reels done (50 comment likes total). Then done with summary."
    ),
    "stories": (
        "Open Instagram story tray. Watch stories from fitness/fashion creators. "
        "like_story on the best 3–8 stories. Skip ads. Human pacing."
    ),
    "feed_engagement": (
        "Scroll home feed. Like strong niche posts. Optionally save 1–2 inspo posts. Stay in budget."
    ),
    "inbox": (
        "Open Instagram inbox. Read primary + requests. "
        "For DMs worth answering, use dm action with Lorena-voice text (max 2 replies per user today). "
        "Skip low-effort hey/hi pings."
    ),
    "comments": (
        "Open activity/notifications. Find comments on @itslorenamor posts. "
        "Reply in Lorena voice — short, sassy. Respect comment budget."
    ),
    "post": (
        "Post one approved reel or carousel from the gallery queue. "
        "Use navigate create, pick media, paste caption, submit (approval required)."
    ),
}


def playbook_text() -> str:
    return _PLAYBOOK


def build_routine(req: RoutineRequest) -> RoutineResponse:
    s = get_settings()
    base = SessionBudget(
        likes_max=s.ugc_likes_max,
        story_likes_max=s.ugc_story_likes_max,
        reels_max=s.ugc_reels_max,
        comments_max=s.ugc_comments_max,
        dms_max=s.ugc_dms_max,
        follows_max=s.ugc_follows_max,
        saves_max=s.ugc_saves_max,
    )
    goal_template = _ROUTINE_GOALS[req.routine]
    goal = goal_template.format(duration=req.duration_minutes)
    if req.routine == "reels_comment_likes":
        base = SessionBudget(
            reels_max=10,
            comment_likes_max=50,
            comment_likes_per_reel=5,
            comments_max=0,
            likes_max=0,
            phase="reels_comment_likes",
        )
    if req.notes:
        goal += f" Notes: {req.notes}"
    if req.mode == "read_only":
        goal += " READ-ONLY: scroll and view only — no likes, comments, DMs, or posts."

    checklists: dict[RoutineKind, list[str]] = {
        "full_session": [
            "Open Instagram",
            "Reels phase: swipe + like niche (budget)",
            "Stories phase: view + like_story (budget)",
            "Feed phase: scroll + like (budget)",
            "Inbox: selective DM replies",
            "Comments: reply on our posts",
            "Done summary",
        ],
        "reels_scroll": ["Navigate reels", "Swipe up through reels", "Like niche posts", "Done"],
        "reels_comment_likes": [
            "Navigate reels tab",
            "Open comments on reel",
            "like_comment x5",
            "press back",
            "swipe up — next reel",
            "Repeat x10 reels",
            "Done summary",
        ],
        "stories": ["Open story tray", "view_story each", "like_story best ones", "Done"],
        "feed_engagement": ["Navigate home", "Scroll feed", "Like/save niche", "Done"],
        "inbox": ["Navigate inbox", "Read threads", "dm selective replies", "Done"],
        "comments": ["Navigate activity", "comment replies", "Done"],
        "post": ["Navigate create", "Select media", "post with caption", "Done"],
    }

    return RoutineResponse(
        goal=goal,
        session_context=base,
        checklist=checklists.get(req.routine, []),
        playbook_excerpt=_PLAYBOOK[:800],
    )
