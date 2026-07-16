"""Reels scroll + comment likes via instagrapi."""

from __future__ import annotations

import logging
import random
from typing import Any

from ..config import get_settings
from .budget import EngagementBudget
from .client import FridayInstagramClient, get_instagram_client
from .web_reels import fetch_reels_web_fallbacks

logger = logging.getLogger(__name__)


def _media_pk(media: Any) -> str:
    return str(getattr(media, "pk", "") or getattr(media, "id", "") or "")


def _fetch_reels(cl: Any, amount: int) -> tuple[list[Any], str]:
    """Try instagrapi reel sources; web cookie sessions often can't use clips/* APIs."""
    errors: list[str] = []
    settings = get_settings()

    for name in ("explore_reels", "reels"):
        fn = getattr(cl, name, None)
        if fn is None:
            continue
        try:
            items = list(fn(amount=amount) or [])
            if items:
                return items[:amount], name
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.debug("Reels fetch %s failed: %s", name, exc)

    tags = [t.strip().lstrip("#") for t in settings.ig_reels_hashtags.split(",") if t.strip()]
    random.shuffle(tags)
    for tag in tags:
        fn = getattr(cl, "hashtag_medias_reels_v1", None)
        if fn is None:
            break
        try:
            items = list(fn(tag, amount=amount) or [])
            if items:
                return items[:amount], f"hashtag_medias_reels_v1(#{tag})"
        except Exception as exc:
            errors.append(f"hashtag #{tag}: {exc}")

    try:
        feed = cl.get_timeline_feed()
        items_raw = feed.get("feed_items") or feed.get("items") or []
        videos: list[Any] = []
        for row in items_raw:
            media = row.get("media_or_ad") or row.get("media") or row
            mt = media.get("media_type") or getattr(media, "media_type", None)
            if mt in (2, 8, "2", "8"):
                videos.append(media)
            elif media.get("product_type") == "clips":
                videos.append(media)
        if videos:
            random.shuffle(videos)
            return videos[:amount], "timeline_feed(videos)"
    except Exception as exc:
        errors.append(f"timeline: {exc}")

    try:
        items, source = fetch_reels_web_fallbacks(cl, amount, tags)
        return items[:amount], source
    except Exception as exc:
        errors.append(f"web: {exc}")

    detail = "; ".join(errors) if errors else "no reel sources returned media"
    raise RuntimeError(
        f"Could not fetch reels ({detail}). "
        "Browser cookies often block mobile clips/* POST — try login-cookies again after warmup, "
        "or use password login once to save a full mobile session."
    )


def _likes_target_for_reel(per_reel: int | None) -> int:
    if per_reel is not None and per_reel > 0:
        return per_reel
    return random.randint(2, 5)


def reels_comment_likes_session(
    *,
    reels_max: int | None = None,
    comment_likes_per_reel: int | None = None,
    read_only: bool | None = None,
    ig: FridayInstagramClient | None = None,
    budget: EngagementBudget | None = None,
) -> dict[str, Any]:
    """
    Scroll reels and like comments on each — API replacement for ADB reels_comment_likes.

    Per reel: dwell → fetch comments → like 2–5 hearts → next reel.
    Stops on session limits or daily caps.
    """
    settings = get_settings()
    read_only = settings.ig_read_only if read_only is None else read_only
    ig = ig or get_instagram_client()
    budget = budget or EngagementBudget()
    cl = ig.client()

    session_reels_max = reels_max if reels_max is not None else settings.ugc_reels_max
    per_reel_default = comment_likes_per_reel

    reels_processed = 0
    comment_likes = 0
    skipped_reels = 0

    block = budget.block_reason()
    if block:
        return {
            "ok": True,
            "stopped": block,
            "reels_processed": 0,
            "comment_likes": 0,
            "read_only": read_only,
        }

    remaining_reels = min(session_reels_max, budget.snapshot().reels_remaining)
    if remaining_reels <= 0:
        return {
            "ok": True,
            "stopped": "daily_reels_cap",
            "reels_processed": 0,
            "comment_likes": 0,
            "read_only": read_only,
        }

    try:
        medias, source = _fetch_reels(cl, amount=max(remaining_reels, 8))
        logger.info("Reels source: %s (%d items)", source, len(medias))
    except Exception as exc:
        return {"ok": False, "error": str(exc), "comment_likes": 0, "reels_processed": 0}

    for media in medias:
        if reels_processed >= remaining_reels:
            break
        if not budget.can_scroll_reel():
            logger.info("Daily reels cap reached")
            break
        if not budget.can_like_comment():
            logger.info("Daily comment-like cap reached")
            break

        media_id = _media_pk(media)
        if not media_id and isinstance(media, dict):
            media_id = str(media.get("pk") or media.get("id") or "")
            continue

        # Dwell on reel (scroll pause)
        dwell = random.uniform(settings.ig_reel_dwell_min, settings.ig_reel_dwell_max)
        logger.info("Reel %d/%d — dwell %.1fs (media=%s)", reels_processed + 1, remaining_reels, dwell, media_id[:12])
        if not read_only:
            ig.human_pause(dwell, dwell + 0.5)
            budget.record_reel_seen()
        else:
            logger.debug("[read-only] dwell %.1fs", dwell)

        reels_processed += 1

        target_likes = _likes_target_for_reel(per_reel_default)
        try:
            comments = cl.media_comments(media_id, amount=target_likes + 4)
        except Exception as exc:
            logger.warning("Comments fetch failed for %s: %s", media_id, exc)
            skipped_reels += 1
            continue

        if not comments:
            skipped_reels += 1
            continue

        random.shuffle(comments)
        liked_this = 0
        for comment in comments:
            if liked_this >= target_likes:
                break
            if not budget.can_like_comment():
                break
            pk = getattr(comment, "pk", None)
            if pk is None:
                continue
            if getattr(comment, "has_liked", False):
                continue

            if read_only:
                liked_this += 1
                comment_likes += 1
                continue

            ig.human_pause(settings.ig_comment_like_delay_min, settings.ig_comment_like_delay_max)
            try:
                if cl.comment_like(int(pk)):
                    budget.record_comment_like()
                    comment_likes += 1
                    liked_this += 1
                    logger.debug("Liked comment %s on reel %s", pk, media_id[:12])
            except Exception as exc:
                logger.debug("comment_like failed: %s", exc)

        # Pause before next reel (scroll)
        if reels_processed < remaining_reels:
            ig.human_pause(settings.ig_reel_scroll_min, settings.ig_reel_scroll_max)

    snap = budget.snapshot()
    return {
        "ok": True,
        "reels_processed": reels_processed,
        "comment_likes": comment_likes,
        "skipped_reels": skipped_reels,
        "read_only": read_only,
        "daily_comment_likes": snap.comment_likes_used,
        "daily_comment_likes_cap": snap.comment_likes_cap,
        "daily_reels_scrolled": snap.reels_scrolled,
        "daily_reels_cap": snap.reels_scrolled_cap,
        "source": source,
    }


# Back-compat alias
like_reels_comments = reels_comment_likes_session
