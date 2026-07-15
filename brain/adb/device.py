"""Device selection, session prep, and stable device_id."""

from __future__ import annotations

from typing import Optional

from . import adb


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


def foreground_app(*, serial: Optional[str] = None) -> tuple[str, str]:
    """Return (package, activity) from dumpsys window."""
    out = adb.shell("dumpsys window windows", serial=serial)
    package = ""
    activity = ""
    for line in out.splitlines():
        line = line.strip()
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            # mCurrentFocus=Window{... u0 com.instagram.android/com.instagram.mainactivity.MainActivity}
            if "/" in line:
                fragment = line.split()[-1].rstrip("}")
                if "/" in fragment:
                    pkg, act = fragment.rsplit("/", 1)
                    package = pkg.strip()
                    activity = act.strip()
                    break
    if not package:
        for line in out.splitlines():
            if "mResumedActivity" in line and "/" in line:
                fragment = line.split()[-1].rstrip("}")
                if "/" in fragment:
                    pkg, act = fragment.rsplit("/", 1)
                    package = pkg.strip()
                    activity = act.strip()
                    break
    return package, activity
