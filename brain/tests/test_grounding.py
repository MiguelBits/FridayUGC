"""Local Gemma vision grounding tests (mock provider, no OpenAI)."""

from __future__ import annotations

import asyncio

from app.agent.actions import GroundRequest, SomMark
from app.agent.grounding import (
    _comments_icon_band_ok,
    _parse_coord,
    _parse_ground_json,
    _rescale_coords,
    ground_target,
)


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
    assert resp.params["x"] == 972
    assert resp.params["y"] == 1344
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
    assert resp.params["x"] < 200
    assert resp.params["y"] > 1600


def test_ground_needs_screenshot_when_empty():
    req = GroundRequest(anchor="comments_icon", screenshot_b64="")
    resp = asyncio.run(ground_target(req))
    assert resp.needs_screenshot is True
    assert not resp.params


def test_ground_som_mark_mock():
    marks = [
        SomMark(mark_id=1, x=990, y=1250, text="comments"),
        SomMark(mark_id=2, x=990, y=1500, text="audio"),
    ]
    req = GroundRequest(
        anchor="comments_icon",
        screenshot_b64="fakeb64",
        screen_width=1080,
        screen_height=2400,
        som_marks=marks,
        use_som=True,
    )
    resp = asyncio.run(ground_target(req))
    assert resp.params.get("mark_id") == 1
    assert resp.params["x"] == 990
    assert resp.confidence >= 0.5


def test_parse_nested_params_json():
    raw = '```json\n{"action":"tap","params":{"x":100,"y":200}}\n```'
    data = _parse_ground_json(raw)
    assert data["params"]["x"] == 100
    assert data["params"]["y"] == 200


def test_rescale_coords_from_image_space():
    x, y = _rescale_coords(345, 384, 345, 768, 1080, 2400)
    assert x == 1080
    assert y == 1200


def test_parse_coord_accepts_string_numbers():
    assert _parse_coord("512") == 512
    assert _parse_coord(512.0) == 512


def test_comments_icon_band_relaxed():
    w, h = 1080, 2400
    assert _comments_icon_band_ok(990, 1344, w, h)
    assert not _comments_icon_band_ok(990, 1500, w, h)
