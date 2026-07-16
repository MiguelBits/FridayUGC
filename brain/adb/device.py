"""Device selection, session prep, and stable device_id."""

from __future__ import annotations

import re
from typing import Optional

from . import adb

_IG_PKG = "com.instagram.android"
_FOCUS_RE = re.compile(r"(com\.[a-z0-9_.]+)/([A-Za-z0-9_.$]+)")


def resolve_serial(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    devices = adb.list_devices()
    if not devices:
        raise adb.AdbError("No authorized ADB devices found (run `adb devices`).")
    if len(devices) > 1:
        raise adb.AdbError(
            f"Multiple devices connected: {devices}. Pass --serial to choose one."
        )
    return devices[0]


def device_id_from_serial(serial: str) -> str:
    return serial.replace(":", "_") if serial else "default"


def session_prep(*, serial: Optional[str] = None) -> None:
    """Keep screen on and wake device for a long USB session."""
    adb.shell("settings put system screen_off_timeout 2147483647", serial=serial)
    adb.shell("svc power stayon usb", serial=serial)
    adb.keyevent("KEYCODE_WAKEUP", serial=serial)


def _parse_pkg_activity(text: str) -> tuple[str, str]:
    for line in text.splitlines():
        lower = line.lower()
        if not any(k in lower for k in ("mcurrentfocus", "mfocusedapp", "mresumedactivity", "mtopfullscreenactivity")):
            continue
        match = _FOCUS_RE.search(line)
        if match:
            return match.group(1), match.group(2)
    return "", ""


def foreground_app(*, serial: Optional[str] = None) -> tuple[str, str]:
    """Return (package, activity) from dumpsys."""
    package, activity = _parse_pkg_activity(adb.shell("dumpsys window", serial=serial))
    if package:
        return package, activity

    package, activity = _parse_pkg_activity(adb.shell("dumpsys activity activities", serial=serial))
    if package:
        return package, activity

    # Last resort: is Instagram in the top activity stack?
    top = adb.shell("dumpsys activity top", serial=serial)
    if _IG_PKG in top:
        match = _FOCUS_RE.search(top)
        if match and _IG_PKG in match.group(1):
            return match.group(1), match.group(2)
        return _IG_PKG, "MainActivity"

    return "", ""


def is_instagram_foreground(*, serial: Optional[str] = None) -> bool:
    pkg, _ = foreground_app(serial=serial)
    return _IG_PKG in pkg
