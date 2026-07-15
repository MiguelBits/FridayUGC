"""Build ObserveBundle from ADB (vision-first, empty element tree in v1)."""

from __future__ import annotations

from typing import Optional

from app.agent.actions import ObserveBundle, Screen

from . import adb
from .device import foreground_app
from .screenshot import IG_PACKAGE, capture_b64

NAV_TABS = {
    "reels": (0.50, 0.965),
    "home": (0.10, 0.965),
    "search": (0.30, 0.965),
    "profile": (0.90, 0.965),
    "inbox": (0.70, 0.965),
    "activity": (0.70, 0.965),
    "create": (0.50, 0.965),
}


def build_observe(
    *,
    serial: Optional[str] = None,
    include_screenshot: bool = True,
    ig_only_screenshot: bool = True,
) -> ObserveBundle:
    width, height = adb.wm_size(serial=serial)
    package, activity = foreground_app(serial=serial)
    shot_b64: str | None = None
    if include_screenshot:
        if not ig_only_screenshot or package == IG_PACKAGE or not package:
            try:
                shot_b64 = capture_b64(serial=serial)
            except adb.AdbError:
                shot_b64 = None
    screen = Screen(
        app=package or "",
        activity=activity or "",
        elements=[],
        screenshot_b64=shot_b64,
    )
    return ObserveBundle(
        screen=screen,
        som_marks=[],
        screen_width=width,
        screen_height=height,
        ig_version="",
    )


def screen_fingerprint(observe: ObserveBundle) -> str:
    s = observe.screen
    return f"{s.app}|{s.activity}|{len(s.elements)}|{observe.screen_width}x{observe.screen_height}"
