"""Build ObserveBundle from ADB (vision-first, empty element tree in v1)."""

from __future__ import annotations

from typing import Optional

from app.agent.actions import ObserveBundle, Screen

from . import adb
from .device import foreground_app, is_instagram_foreground
from .screenshot import IG_PACKAGE, capture_b64, capture_png


def build_observe(
    *,
    serial: Optional[str] = None,
    include_screenshot: bool = True,
    ig_only_screenshot: bool = True,
) -> ObserveBundle:
    width, height = adb.wm_size(serial=serial)
    package, activity = foreground_app(serial=serial)
    if not package and include_screenshot:
        # dumpsys can lag after open_app — trust screencap when IG is visible.
        try:
            capture_png(serial=serial)
            if is_instagram_foreground(serial=serial):
                package, activity = foreground_app(serial=serial)
        except adb.AdbError:
            pass
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
