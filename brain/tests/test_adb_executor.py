"""Tests for ADB action executor (mocked subprocess)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from adb.executor import READ_ONLY_BLOCKED, execute, settle_ms
from adb.safety_zones import story_tray_blocked
from adb.validate import validate_tap


@pytest.mark.parametrize("action", sorted(READ_ONLY_BLOCKED))
def test_read_only_blocks_engagement(action):
    result = execute(action, {"x": 540, "y": 1200}, screen_width=1080, screen_height=2400, mode="read_only")
    assert not result.ok
    assert "read_only" in (result.error or "")


def test_tap_calls_adb_with_jitter():
    with patch("adb.gestures.adb.tap") as mock_tap:
        result = execute("tap", {"x": 500, "y": 1500}, screen_width=1080, screen_height=2400)
    assert result.ok
    mock_tap.assert_called_once()
    args = mock_tap.call_args[0]
    assert abs(args[0] - 500) <= 4
    assert abs(args[1] - 1500) <= 4


def test_story_tray_blocked():
    assert story_tray_blocked(540, 400, 2400)
    assert not story_tray_blocked(540, 800, 2400)


def test_validate_tap_rejects_story_tray():
    err = validate_tap(540, 400, 1080, 2400)
    assert err is not None
    assert "story tray" in err


def test_press_back():
    with patch("adb.executor.adb.keyevent") as mock_key:
        result = execute("press", {"key": "back"}, screen_width=1080, screen_height=2400)
    assert result.ok
    mock_key.assert_called_once_with(4, serial=None)


def test_wait_sleeps():
    with patch("adb.executor.time.sleep") as mock_sleep:
        result = execute("wait", {"ms": 1200}, screen_width=1080, screen_height=2400)
    assert result.ok
    mock_sleep.assert_called_once_with(1.2)


def test_open_app_monkey():
    with patch("adb.executor.adb.shell") as mock_shell:
        result = execute("open_app", {"package": "com.instagram.android"}, screen_width=1080, screen_height=2400)
    assert result.ok
    mock_shell.assert_called_once()
    assert "monkey" in mock_shell.call_args[0][0]


def test_navigate_reels_deeplink():
    with patch("adb.executor.adb.shell") as mock_shell:
        result = execute("navigate", {"tab": "reels"}, screen_width=1080, screen_height=2400)
    assert result.ok
    assert "instagram://reels" in mock_shell.call_args[0][0]


def test_settle_ms_defaults():
    assert settle_ms("open_app") == 4500
    assert settle_ms("unknown_action") == 500
