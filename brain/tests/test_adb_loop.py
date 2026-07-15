"""Tests for ADB thin-client loop (mocked brain + adb)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adb.loop import LoopConfig, _prompt_approval, run_loop
from app.agent.actions import ObserveBundle, Screen, TickResponse
from app.ugc.operator import RoutineResponse, SessionBudget


def _observe(**_kwargs) -> ObserveBundle:
    return ObserveBundle(
        screen=Screen(app="com.instagram.android", activity="MainActivity", elements=[]),
        screen_width=1080,
        screen_height=2400,
    )


def test_loop_stops_on_done():
    tick_responses = [
        TickResponse(action="wait", params={"ms": 10}, reason="settle"),
        TickResponse(action="done", params={"summary": "ok"}, reason="finished", done=True),
    ]

    async def fake_tick(request):
        return tick_responses.pop(0)

    mock_client = MagicMock()
    mock_client.health = AsyncMock(return_value={"status": "ok"})
    mock_client.get_memory = AsyncMock(return_value=MagicMock(entries=[]))
    mock_client.tick = AsyncMock(side_effect=fake_tick)
    mock_client.post_trajectory = AsyncMock(return_value=MagicMock(accepted=1, failures_recorded=0))

    config = LoopConfig(
        brain_url="http://test",
        token="tok",
        goal="Open Instagram",
        max_steps=10,
        serial="emulator-5554",
    )

    with (
        patch("adb.loop.resolve_serial", return_value="emulator-5554"),
        patch("adb.loop.session_prep"),
        patch("adb.loop.build_observe", side_effect=_observe),
        patch("adb.loop.execute", return_value=MagicMock(ok=True, ui_key="", error=None)),
        patch("adb.loop.BrainClient", return_value=mock_client),
        patch("adb.loop.time.sleep"),
    ):
        state = asyncio.run(run_loop(config))

    assert state.step == 1
    assert mock_client.tick.await_count == 2


def test_circuit_breaker_on_tick_failures():
    mock_client = MagicMock()
    mock_client.health = AsyncMock(return_value={"status": "ok"})
    mock_client.get_memory = AsyncMock(return_value=MagicMock(entries=[]))
    mock_client.tick = AsyncMock(side_effect=RuntimeError("brain down"))
    mock_client.post_trajectory = AsyncMock()

    config = LoopConfig(
        brain_url="http://test",
        token="tok",
        goal="Open Instagram",
        max_steps=20,
        serial="device-1",
    )

    with (
        patch("adb.loop.resolve_serial", return_value="device-1"),
        patch("adb.loop.session_prep"),
        patch("adb.loop.build_observe", side_effect=_observe),
        patch("adb.loop.execute", return_value=MagicMock(ok=True, ui_key="", error=None)),
        patch("adb.loop.BrainClient", return_value=mock_client),
        patch("adb.loop.time.sleep"),
    ):
        state = asyncio.run(run_loop(config))

    assert state.consecutive_failures >= 8
    assert mock_client.tick.await_count == 13


def test_prompt_approval_rejects_by_default(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert not _prompt_approval("comment", {"text": "hi"})


def test_prompt_approval_accepts_yes(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert _prompt_approval("comment", {"text": "hi"})


def test_routine_hydrates_goal():
    mock_client = MagicMock()
    mock_client.health = AsyncMock(return_value={"status": "ok"})
    mock_client.get_memory = AsyncMock(return_value=MagicMock(entries=[]))
    mock_client.routine = AsyncMock(
        return_value=RoutineResponse(
            goal="Comment likes on reels",
            session_context=SessionBudget(comment_likes_max=50),
            checklist=["open reels"],
        )
    )
    mock_client.tick = AsyncMock(
        return_value=TickResponse(action="done", params={}, reason="done", done=True)
    )
    mock_client.post_trajectory = AsyncMock(return_value=MagicMock(accepted=0, failures_recorded=0))

    config = LoopConfig(
        brain_url="http://test",
        token="tok",
        goal="ignored",
        routine="reels_comment_likes",
        serial="dev",
    )

    with (
        patch("adb.loop.resolve_serial", return_value="dev"),
        patch("adb.loop.session_prep"),
        patch("adb.loop.build_observe", side_effect=_observe),
        patch("adb.loop.BrainClient", return_value=mock_client),
    ):
        asyncio.run(run_loop(config))

    mock_client.routine.assert_awaited_once()
