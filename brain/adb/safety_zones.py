"""Tap safety zones — block accidental story-tray hits."""

from __future__ import annotations

STORY_TRAY_Y_FRACTION = 0.28


def story_tray_blocked(x: int, y: int, screen_height: int) -> bool:
    if screen_height <= 0:
        return False
    return y < int(screen_height * STORY_TRAY_Y_FRACTION)


def block_reason(x: int, y: int, screen_width: int, screen_height: int) -> str | None:
    if x < 0 or y < 0 or (screen_width > 0 and x > screen_width) or (screen_height > 0 and y > screen_height):
        return f"coordinates ({x},{y}) out of bounds {screen_width}x{screen_height}"
    if story_tray_blocked(x, y, screen_height):
        return f"tap y={y} blocked (story tray zone y < {STORY_TRAY_Y_FRACTION:.0%} height)"
    return None
