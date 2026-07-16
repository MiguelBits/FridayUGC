"""Dispatch action_protocol actions via ADB."""

from __future__ import annotations

import shlex
import time
from typing import Any, Optional

from app.agent.actions import ActionName

from . import adb
from .gestures import comments_sheet_scroll, ig_nav_tap, reels_next_swipe, scroll_direction, tap_jittered
from .nav import IG_NAV_X, nav_xy
from .screenshot import IG_PACKAGE
from .validate import validate_tap

KEY_MAP = {
    "back": 4,
    "home": 3,
    "enter": 66,
    "recents": 187,
}

SETTLE_MS: dict[str, int] = {
    "open_app": 4500,
    "navigate": 2800,
    "open_reels": 2800,
    "swipe": 900,
    "scroll": 900,
    "press": 700,
    "like_comment": 650,
    "tap": 650,
}

READ_ONLY_BLOCKED: frozenset[str] = frozenset(
    {
        "post",
        "comment",
        "dm",
        "follow",
        "unfollow",
        "like",
        "like_story",
        "like_comment",
        "save",
        "type",
    }
)


class ExecutorResult:
    def __init__(self, ok: bool, error: str | None = None, ui_key: str = ""):
        self.ok = ok
        self.error = error
        self.ui_key = ui_key


def settle_ms(action: str) -> int:
    return SETTLE_MS.get(action, 500)


def _clipboard_type(text: str, *, serial: Optional[str] = None) -> None:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    adb.shell(f'cmd clipboard set "{escaped}"', serial=serial)
    adb.keyevent(279, serial=serial)


def execute(
    action: ActionName,
    params: dict[str, Any],
    *,
    screen_width: int,
    screen_height: int,
    serial: Optional[str] = None,
    mode: str = "read_only",
) -> ExecutorResult:
    if mode == "read_only" and action in READ_ONLY_BLOCKED:
        return ExecutorResult(False, f"read_only blocks action '{action}'")

    ui_key = str(params.get("ui_key") or "")

    if action in {"done", "fail"}:
        return ExecutorResult(True, ui_key=ui_key)

    if action == "wait":
        ms = int(params.get("ms") or 800)
        time.sleep(ms / 1000.0)
        return ExecutorResult(True, ui_key=ui_key)

    if action == "tap" or action in {"like", "like_story", "like_comment", "save", "follow", "unfollow", "view_story"}:
        x = int(params.get("x") or 0)
        y = int(params.get("y") or 0)
        if x <= 0 or y <= 0:
            return ExecutorResult(False, "tap requires x,y coordinates from brain grounding")
        err = validate_tap(x, y, screen_width, screen_height)
        if err:
            return ExecutorResult(False, err, ui_key=ui_key)
        tap_jittered(x, y, serial=serial)
        return ExecutorResult(True, ui_key=ui_key)

    if action == "scroll":
        direction = str(params.get("direction") or "down")
        scroll_direction(direction, screen_width, screen_height, serial=serial)
        return ExecutorResult(True, ui_key=ui_key)

    if action == "swipe":
        direction = str(params.get("direction") or "up")
        zone = str(params.get("zone") or "").lower()
        if zone == "reels_rail" or (direction == "up" and params.get("ui_key") == "reels_next"):
            reels_next_swipe(screen_width, screen_height, serial=serial)
        elif params.get("intent") == "comments_scroll" or zone == "comments_sheet":
            comments_sheet_scroll(screen_width, screen_height, serial=serial)
        elif direction == "up" or zone in {"reels", "reels_rail"}:
            reels_next_swipe(screen_width, screen_height, serial=serial)
        else:
            scroll_direction(direction if direction in {"up", "down", "left", "right"} else "up", screen_width, screen_height, serial=serial)
        return ExecutorResult(True, ui_key=ui_key)

    if action == "press":
        key = str(params.get("key") or "back")
        code = KEY_MAP.get(key, key)
        adb.keyevent(code, serial=serial)
        return ExecutorResult(True, ui_key=ui_key)

    if action == "open_app":
        package = str(params.get("package") or IG_PACKAGE)
        adb.shell(f"monkey -p {shlex.quote(package)} 1", serial=serial)
        return ExecutorResult(True, ui_key=ui_key)

    if action == "open_reels":
        return execute(
            "navigate",
            {"tab": "reels"},
            screen_width=screen_width,
            screen_height=screen_height,
            serial=serial,
            mode=mode,
        )

    if action == "navigate":
        tab = str(params.get("tab") or "home")
        if tab == "reels":
            # Deeplink alone is unreliable on many IG builds — always tap the Reels tab too.
            try:
                adb.shell(
                    "am start -a android.intent.action.VIEW -d instagram://reels "
                    "com.instagram.android",
                    serial=serial,
                )
            except adb.AdbError:
                pass
            x, y = nav_xy("reels", screen_width, screen_height)
            err = validate_tap(x, y, screen_width, screen_height)
            if err:
                return ExecutorResult(False, err, ui_key="nav_reels")
            ig_nav_tap("reels", screen_width, screen_height, serial=serial)
            return ExecutorResult(True, ui_key="nav_reels")
        x, y = nav_xy(tab, screen_width, screen_height)
        if tab in IG_NAV_X:
            err = validate_tap(x, y, screen_width, screen_height)
            if err:
                return ExecutorResult(False, err, ui_key=f"nav_{tab}")
            ig_nav_tap(tab, screen_width, screen_height, serial=serial)
            return ExecutorResult(True, ui_key=f"nav_{tab}")
        return ExecutorResult(False, f"unknown navigate tab '{tab}'")

    if action == "type":
        text = str(params.get("text") or "")
        if not text:
            return ExecutorResult(False, "type requires text")
        try:
            _clipboard_type(text, serial=serial)
        except adb.AdbError as exc:
            return ExecutorResult(False, f"clipboard type failed: {exc}")
        return ExecutorResult(True, ui_key=ui_key)

    if action in {"post", "comment", "dm"}:
        return ExecutorResult(False, f"action '{action}' not implemented in ADB executor v1")

    if action == "intent":
        name = str(params.get("name") or "")
        if name in {"enter_reels", "open_reels"}:
            return execute(
                "navigate",
                {"tab": "reels"},
                screen_width=screen_width,
                screen_height=screen_height,
                serial=serial,
                mode=mode,
            )
        if name in {"reels_next", "next_reel", "watch_reel"}:
            reels_next_swipe(screen_width, screen_height, serial=serial)
            return ExecutorResult(True, ui_key=name)
        if name in {"comments_scroll", "scroll_comments"}:
            comments_sheet_scroll(screen_width, screen_height, serial=serial)
            return ExecutorResult(True, ui_key=name)
        return ExecutorResult(False, f"unknown intent '{name}'")

    return ExecutorResult(False, f"unsupported action '{action}'")
