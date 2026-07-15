"""Post-action verification — brain-side (replaces phone OutcomeVerifier for tick v2)."""

from __future__ import annotations

from .actions import Screen, ScreenState, TickLastResult
from .perception import classify_screen, is_full_comments_sheet, on_reels_surface


def _fp(screen: Screen) -> str:
    parts = [screen.app, screen.activity]
    for e in screen.elements[:40]:
        parts.append(f"{e.id}:{e.text}:{e.x}:{e.y}")
    return "|".join(parts)


def change_score(before: Screen, after: Screen) -> float:
    if _fp(before) == _fp(after):
        return 0.0
    return min(1.0, abs(len(before.elements) - len(after.elements)) * 0.05 + 0.1)


def verify_last(result: TickLastResult, activity: str = "") -> tuple[str, float]:
    """Return (verified status, change_score)."""
    if not result.action:
        return "unknown", 0.0
    if not result.executor_ok:
        return "failed", 0.0

    before = result.before_observe.screen if result.before_observe else Screen()
    after = result.after_observe.screen if result.after_observe else Screen()
    score = change_score(before, after)
    ui_key = (result.ui_key or "").strip()
    act = activity or after.activity or before.activity

    if result.action in {"wait", "press"}:
        return "unknown", score

    if result.action == "open_app":
        opened = "instagram" in (after.app or "").lower()
        return ("verified" if opened else "unverified"), score

    if result.action in {"swipe", "scroll"}:
        zone = (result.params.get("zone") or "").lower()
        if zone == "reels_rail":
            return "verified", score
        return ("verified" if score >= 0.12 else "unverified"), score

    if result.action in {"tap", "like", "like_story", "like_comment"}:
        if ui_key == "comments_icon":
            ok = is_full_comments_sheet(after, act) or score >= 0.10
            return ("verified" if ok else "unverified"), score
        if ui_key == "comment_heart" or result.action == "like_comment":
            ok = is_full_comments_sheet(after, act)
            return ("verified" if ok else "unverified"), score
        if ui_key == "nav_reels":
            state = classify_screen(after)
            ok = on_reels_surface(state, {}, after) or score >= 0.08
            return ("verified" if ok else "unverified"), score
        return ("verified" if score >= 0.06 else "unverified"), score

    if result.action in {"navigate", "open_reels"}:
        state = classify_screen(after)
        ok = on_reels_surface(state, {}, after) or score >= 0.08
        return ("verified" if ok else "unverified"), score

    return ("verified" if score >= 0.05 else "unknown"), score
