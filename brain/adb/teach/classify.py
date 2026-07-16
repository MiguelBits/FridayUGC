"""Strict surface scoring for teach labels and replay (text-based, no change_score)."""

from __future__ import annotations

from typing import Any

from app.agent.actions import Screen
from app.agent.flows.ads import is_sponsored_ad, is_trap_overlay, looks_like_comments_sheet
from app.agent.flows.surface import SurfaceLabel, classify_surface, has_share_sheet_signals


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
)


def _screen_from_texts(texts: list[str]) -> Screen:
    """Build a minimal Screen with text elements so share-sheet helpers can fire."""
    elements = []
    for i, t in enumerate(texts or []):
        if not t:
            continue
        from app.agent.actions import ScreenElement

        elements.append(ScreenElement(id=i + 1, text=str(t), clickable=False))
    return Screen(elements=elements)


def score_open_comments(
    after_texts: list[str],
    *,
    before_texts: list[str] | None = None,
    activity: str = "",
) -> dict[str, Any]:
    """Return {ok, label_guess, surface} for open_comments replay / suggestion."""
    after = list(after_texts or [])
    before = list(before_texts or [])
    screen = _screen_from_texts(after)

    if is_trap_overlay(screen, after):
        return {"ok": False, "label_guess": "trap", "surface": SurfaceLabel.TRAP.value}
    if has_share_sheet_signals(screen) or _share_from_joined(after):
        if not looks_like_comments_sheet(screen, after):
            return {
                "ok": False,
                "label_guess": "wrong_sheet",
                "surface": SurfaceLabel.SHARE_SHEET.value,
            }
    if looks_like_comments_sheet(screen, after):
        return {"ok": True, "label_guess": "ok", "surface": SurfaceLabel.COMMENTS_SHEET.value}

    label = classify_surface(screen, activity=activity, extra_texts=after)
    if label == SurfaceLabel.COMMENTS_SHEET:
        return {"ok": True, "label_guess": "ok", "surface": label.value}
    if label == SurfaceLabel.SHARE_SHEET:
        return {"ok": False, "label_guess": "wrong_sheet", "surface": label.value}
    if label == SurfaceLabel.TRAP:
        return {"ok": False, "label_guess": "trap", "surface": label.value}
    if label == SurfaceLabel.AD_REEL or is_sponsored_ad(screen, after) or is_sponsored_ad(
        _screen_from_texts(before), before
    ):
        return {"ok": False, "label_guess": "ad", "surface": SurfaceLabel.AD_REEL.value}
    return {"ok": False, "label_guess": "fail", "surface": label.value}


def _share_from_joined(texts: list[str]) -> bool:
    joined = " ".join(t.lower() for t in texts)
    hits = sum(1 for h in SHARE_TEXT_HINTS if h in joined)
    return hits >= 1


def is_ad_reel(texts: list[str]) -> bool:
    screen = _screen_from_texts(texts)
    return is_sponsored_ad(screen, texts)
