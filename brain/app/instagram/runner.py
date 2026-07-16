"""Map Friday operator routines to instagrapi workers."""

from __future__ import annotations

import logging
from typing import Any, Literal

from ..config import get_settings
from .engagement import reels_comment_likes_session

logger = logging.getLogger(__name__)

RoutineKind = Literal[
    "full_session",
    "reels_scroll",
    "reels_comment_likes",
    "stories",
    "feed_engagement",
    "inbox",
    "comments",
    "post",
    "post_reel",
    "post_story",
    "warmup",
]


def run_routine(
    kind: RoutineKind,
    *,
    mode: str = "full",
    reels_max: int | None = None,
    comment_likes_per_reel: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    read_only = mode == "read_only" or settings.ig_read_only

    if kind not in {"reels_comment_likes", "reels_scroll"}:
        return {
            "ok": False,
            "error": f"Routine {kind!r} not implemented on API path yet — use reels_comment_likes",
        }

    reels_max = reels_max or settings.ugc_reels_max
    if kind == "reels_scroll":
        reels_max = min(reels_max, 8)

    logger.info("Running %s (read_only=%s reels_max=%s)", kind, read_only, reels_max)
    return reels_comment_likes_session(
        reels_max=reels_max,
        comment_likes_per_reel=comment_likes_per_reel,
        read_only=read_only,
    )
