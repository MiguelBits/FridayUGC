"""Local Gemma vision grounding tests (mock provider, no OpenAI)."""

from __future__ import annotations

import asyncio

from app.agent.actions import GroundRequest
from app.agent.grounding import ground_target


def test_ground_comments_icon_mock():
    req = GroundRequest(
        anchor="comments_icon",
        screenshot_b64="fakeb64",
        screen_width=1080,
        screen_height=2400,
        screen_type="reels_viewer",
    )
    resp = asyncio.run(ground_target(req))
    assert resp.action == "tap"
    assert "x" in resp.params and "y" in resp.params
    assert resp.confidence >= 0.5


def test_ground_comment_heart_mock():
    req = GroundRequest(
        anchor="comment_heart",
        screenshot_b64="fakeb64",
        screen_width=1080,
        screen_height=2400,
        screen_type="comments_sheet",
        row_index=2,
    )
    resp = asyncio.run(ground_target(req))
    assert resp.action == "like_comment"
    assert resp.params["y"] > 1400


def test_ground_needs_screenshot_when_empty():
    req = GroundRequest(anchor="comments_icon", screenshot_b64="")
    resp = asyncio.run(ground_target(req))
    assert resp.needs_screenshot is True
    assert not resp.params
