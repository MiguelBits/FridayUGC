"""Deterministic Instagram flow defs + surface heuristics."""

from __future__ import annotations

import base64
import io

from app.agent.actions import Screen
from app.agent.flows.defs import (
    COMMENTS_BAND_SHARE_FLOOR,
    FLOW_OPEN_COMMENTS,
    FLOW_OPEN_REELS,
    comments_icon_xy,
)
from app.agent.flows.surface import SurfaceLabel, classify_surface, has_share_sheet_signals
from app.agent.grounding import _comments_icon_band_ok
from app.agent.verifier import verify_last
from app.agent.actions import ObserveBundle, TickLastResult


def test_flow_defs_exist():
    assert FLOW_OPEN_REELS.steps[0].action == "navigate"
    assert FLOW_OPEN_COMMENTS.steps[0].anchor == "comments_icon"


def test_comments_icon_xy_above_share_floor():
    x, y = comments_icon_xy(1080, 2400)
    assert x == 972
    assert y == 1248  # 0.52 * 2400
    assert y < int(2400 * COMMENTS_BAND_SHARE_FLOOR)


def test_comments_band_rejects_share_zone():
    w, h = 1080, 2400
    assert _comments_icon_band_ok(990, 1248, w, h)
    assert _comments_icon_band_ok(990, 1400, w, h)  # tall-phone comments zone
    assert not _comments_icon_band_ok(990, 1600, w, h)  # >= 0.64 share floor


def test_share_sheet_signals():
    screen = Screen(
        app="com.instagram.android",
        elements=[
            {"id": 0, "text": "Repost", "role": "button"},
            {"id": 1, "text": "Add to story", "role": "button"},
            {"id": 2, "text": "Copy link", "role": "button"},
        ],
    )
    assert has_share_sheet_signals(screen)
    assert classify_surface(screen) == SurfaceLabel.SHARE_SHEET


def test_comments_a11y_not_share():
    screen = Screen(
        app="com.instagram.android",
        elements=[
            {"id": 0, "text": "Reply", "role": "button"},
            {"id": 1, "text": "Add a comment...", "role": "edit"},
        ],
    )
    assert classify_surface(screen) == SurfaceLabel.COMMENTS_SHEET


def _white_bottom_b64() -> str:
    from PIL import Image

    img = Image.new("RGB", (108, 240), (20, 20, 20))
    for y in range(120, 240):
        for x in range(108):
            img.putpixel((x, y), (245, 245, 245))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_comments_requires_text_not_bright_pixels_alone():
    """Cookie/ad pages are bright — pixels alone must not count as comments."""
    screen = Screen(app="com.instagram.android", activity="ClipsViewerActivity", elements=[])
    shot = _white_bottom_b64()
    assert classify_surface(screen, screenshot_b64=shot) != SurfaceLabel.COMMENTS_SHEET
    assert (
        classify_surface(screen, screenshot_b64=shot, extra_texts=["Comentários", "Responder"])
        == SurfaceLabel.COMMENTS_SHEET
    )


def test_sponsored_ad_detected():
    from app.agent.flows.ads import is_sponsored_ad

    screen = Screen(app="com.instagram.android", elements=[])
    assert is_sponsored_ad(screen, ["Patrocinado", "Ver detalhes", "verisure.portugal"])
    assert not is_sponsored_ad(screen, ["Remix", "Comentários"])


def test_verify_comments_icon_rejects_share_change_only():
    before = Screen(app="com.instagram.android", activity="ClipsViewerActivity", elements=[])
    after = Screen(
        app="com.instagram.android",
        activity="ClipsViewerActivity",
        elements=[
            {"id": 0, "text": "Repost", "role": "button"},
            {"id": 1, "text": "Copy link", "role": "button"},
        ],
    )
    result = TickLastResult(
        action="tap",
        executor_ok=True,
        ui_key="comments_icon",
        before_observe=ObserveBundle(screen=before),
        after_observe=ObserveBundle(screen=after),
    )
    verified, _ = verify_last(result, after.activity)
    assert verified == "unverified"
