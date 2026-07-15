"""Human-like gesture helpers with small jitter."""

from __future__ import annotations

import random
from typing import Optional

from . import adb

JITTER_PX = 4


def jitter(x: int, y: int, px: int = JITTER_PX) -> tuple[int, int]:
    return x + random.randint(-px, px), y + random.randint(-px, px)


def tap_jittered(x: int, y: int, *, serial: Optional[str] = None) -> tuple[int, int]:
    jx, jy = jitter(x, y)
    adb.tap(jx, jy, serial=serial)
    return jx, jy


def reels_next_swipe(screen_width: int, screen_height: int, *, serial: Optional[str] = None) -> None:
    x = int(screen_width * 0.85)
    y1 = int(screen_height * 0.52)
    y2 = int(screen_height * 0.22)
    adb.swipe(x, y1, x, y2, 280, serial=serial)


def comments_sheet_scroll(screen_width: int, screen_height: int, *, serial: Optional[str] = None) -> None:
    x = int(screen_width * 0.50)
    y1 = int(screen_height * 0.78)
    y2 = int(screen_height * 0.58)
    adb.swipe(x, y1, x, y2, 320, serial=serial)


def scroll_direction(
    direction: str,
    screen_width: int,
    screen_height: int,
    *,
    serial: Optional[str] = None,
) -> None:
    cx = screen_width // 2
    if direction == "down":
        adb.swipe(cx, int(screen_height * 0.72), cx, int(screen_height * 0.32), 350, serial=serial)
    elif direction == "up":
        adb.swipe(cx, int(screen_height * 0.32), cx, int(screen_height * 0.72), 350, serial=serial)
    elif direction == "left":
        adb.swipe(int(screen_width * 0.78), screen_height // 2, int(screen_width * 0.22), screen_height // 2, 350, serial=serial)
    elif direction == "right":
        adb.swipe(int(screen_width * 0.22), screen_height // 2, int(screen_width * 0.78), screen_height // 2, 350, serial=serial)
    else:
        reels_next_swipe(screen_width, screen_height, serial=serial)
