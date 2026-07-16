"""Classify Instagram surfaces from a11y + screenshot pixels (ADB has empty trees)."""

from __future__ import annotations

import base64
import io
from enum import Enum
from typing import Any

from ..actions import Screen
from ..perception import has_comments_sheet_signals, is_full_comments_sheet
from .ads import is_home_feed_surface, is_sponsored_ad, is_trap_overlay, looks_like_comments_sheet


class SurfaceLabel(str, Enum):
    REELS_VIEWER = "reels_viewer"
    COMMENTS_SHEET = "comments_sheet"
    SHARE_SHEET = "wrong_sheet_share"
    AD_REEL = "ad_reel"
    HOME_FEED = "home_feed"
    TRAP = "trap_overlay"
    UNKNOWN = "unknown"
    OTHER = "other"


SHARE_TEXT_HINTS = (
    "repost",
    "add to story",
    "add to your story",
    "copy link",
    "share to",
    "send to",
    "share reel",
    "whatsapp",
    "messenger",
    "share profile",
)


def has_share_sheet_signals(screen: Screen) -> bool:
    texts = [e.text.lower() for e in screen.elements if e.text]
    if not texts:
        return False
    joined = " ".join(texts)
    hits = sum(1 for h in SHARE_TEXT_HINTS if h in joined)
    if hits >= 1 and not has_comments_sheet_signals(screen):
        return True
    if any("repost" in t for t in texts):
        return True
    return False


def _bottom_sheet_lightness(screenshot_b64: str) -> dict[str, float]:
    """Return brightness stats for bottom half vs top half of the frame."""
    empty = {"bottom_mean": 0.0, "top_mean": 0.0, "bottom_light_frac": 0.0}
    if not screenshot_b64:
        return empty
    try:
        from PIL import Image, ImageStat

        raw = base64.b64decode(screenshot_b64, validate=False)
        with Image.open(io.BytesIO(raw)) as img:
            gray = img.convert("L")
            w, h = gray.size
            if w < 8 or h < 8:
                return empty
            top = gray.crop((0, 0, w, int(h * 0.42)))
            bottom = gray.crop((0, int(h * 0.48), w, h))
            top_mean = float(ImageStat.Stat(top).mean[0])
            bot_mean = float(ImageStat.Stat(bottom).mean[0])
            hist = bottom.histogram()
            light = sum(hist[160:])
            total = max(1, sum(hist))
            return {
                "bottom_mean": bot_mean,
                "top_mean": top_mean,
                "bottom_light_frac": light / total,
            }
    except (ValueError, OSError, ImportError):
        return empty


def comments_sheet_from_pixels(screenshot_b64: str) -> bool:
    """Heuristic only — prefer uiautomator text. Bright bottom alone is NOT enough (ads/cookies)."""
    stats = _bottom_sheet_lightness(screenshot_b64)
    # Require a strong white sheet AND a relatively dark top (reel still visible above).
    if stats["bottom_light_frac"] >= 0.45 and stats["bottom_mean"] >= 170 and stats["top_mean"] < 140:
        return True
    return False


def classify_surface(
    screen: Screen,
    *,
    screenshot_b64: str = "",
    activity: str = "",
    extra_texts: list[str] | None = None,
) -> SurfaceLabel:
    act = (activity or screen.activity or "").lower()
    texts = extra_texts or []

    if is_trap_overlay(screen, texts):
        return SurfaceLabel.TRAP
    if is_home_feed_surface(screen, texts):
        return SurfaceLabel.HOME_FEED
    if looks_like_comments_sheet(screen, texts) or (
        is_full_comments_sheet(screen, act) and not is_trap_overlay(screen, texts)
    ):
        return SurfaceLabel.COMMENTS_SHEET
    if has_share_sheet_signals(screen):
        return SurfaceLabel.SHARE_SHEET
    if is_sponsored_ad(screen, texts):
        return SurfaceLabel.AD_REEL

    # Pixel path is weak alone — never call bright cookies "comments" without text.
    if texts and looks_like_comments_sheet(screen, texts):
        return SurfaceLabel.COMMENTS_SHEET
    if not screen.elements and not texts and screenshot_b64:
        # Without uiautomator text, refuse to claim comments_sheet from pixels only.
        pass

    if "clips" in act or ("reel" in act and "profile" not in act):
        return SurfaceLabel.REELS_VIEWER
    if screen.app and "instagram" not in (screen.app or "").lower():
        return SurfaceLabel.OTHER
    return SurfaceLabel.UNKNOWN


def comments_open_ok(
    screen: Screen,
    *,
    screenshot_b64: str = "",
    activity: str = "",
    extra_texts: list[str] | None = None,
) -> bool:
    label = classify_surface(
        screen, screenshot_b64=screenshot_b64, activity=activity, extra_texts=extra_texts
    )
    return label == SurfaceLabel.COMMENTS_SHEET


def wrong_sheet(
    screen: Screen,
    *,
    screenshot_b64: str = "",
    activity: str = "",
    extra_texts: list[str] | None = None,
) -> bool:
    label = classify_surface(
        screen, screenshot_b64=screenshot_b64, activity=activity, extra_texts=extra_texts
    )
    return label in {SurfaceLabel.SHARE_SHEET, SurfaceLabel.TRAP}


def surface_signals(
    screen: Screen,
    *,
    screenshot_b64: str = "",
    extra_texts: list[str] | None = None,
) -> dict[str, Any]:
    label = classify_surface(screen, screenshot_b64=screenshot_b64, extra_texts=extra_texts)
    stats = _bottom_sheet_lightness(screenshot_b64)
    return {
        "label": label.value,
        **stats,
        "a11y_comments": has_comments_sheet_signals(screen),
        "extra_text_n": len(extra_texts or []),
        "is_ad": is_sponsored_ad(screen, extra_texts),
    }
