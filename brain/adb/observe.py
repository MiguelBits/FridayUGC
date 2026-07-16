"""Build ObserveBundle from ADB (screenshot + light uiautomator text)."""

from __future__ import annotations

from typing import Optional

from app.agent.actions import ObserveBundle, Screen, ScreenElement

from . import adb
from .device import foreground_app, is_instagram_foreground
from .screenshot import IG_PACKAGE, capture_b64, capture_png
from .uiauto import dump_texts


def build_observe(
    *,
    serial: Optional[str] = None,
    include_screenshot: bool = True,
    ig_only_screenshot: bool = True,
    include_ui_texts: bool = True,
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
    elements: list[ScreenElement] = []
    if include_ui_texts:
        try:
            for i, text in enumerate(dump_texts(serial=serial, limit=60)):
                elements.append(ScreenElement(id=i, text=text, role="text", clickable=False))
        except Exception:
            elements = []
    screen = Screen(
        app=package or "",
        activity=activity or "",
        elements=elements,
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
