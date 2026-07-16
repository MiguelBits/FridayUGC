"""Tests for Instagram API transport (mocked instagrapi)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.instagram.client import FridayInstagramClient
from app.instagram.poster import _build_caption


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_build_caption_appends_hashtags():
    item = {"caption": "Miami gym fit", "hashtags": ["fitness", "miami"]}
    text = _build_caption(item)
    assert "Miami gym fit" in text
    assert "#fitness" in text
    assert "#miami" in text


def test_doctor_fails_without_credentials(monkeypatch):
    monkeypatch.setenv("FRIDAY_IG_USERNAME", "")
    monkeypatch.setenv("FRIDAY_IG_PASSWORD", "")
    monkeypatch.setenv("FRIDAY_IG_SESSION_JSON", "")
    get_settings.cache_clear()
    rows = FridayInstagramClient().doctor()
    cred = next(r for r in rows if r["check"] == "credentials")
    assert cred["status"] == "fail"


def test_client_loads_saved_session(tmp_path, monkeypatch):
    session_file = tmp_path / "session.json"
    session_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("FRIDAY_IG_USERNAME", "lorena")
    monkeypatch.setenv("FRIDAY_IG_PASSWORD", "secret")
    monkeypatch.setenv("FRIDAY_IG_SESSION_PATH", str(session_file))
    get_settings.cache_clear()

    mock_cl = MagicMock()
    with patch("instagrapi.Client", return_value=mock_cl):
        ig = FridayInstagramClient()
        cl = ig.load()

    assert cl is mock_cl
    mock_cl.load_settings.assert_called_once_with(session_file)
    mock_cl.account_info.assert_called_once()
    mock_cl.login.assert_not_called()


def test_post_due_dry_run(monkeypatch, tmp_path):
    monkeypatch.setenv("FRIDAY_IG_READ_ONLY", "true")
    get_settings.cache_clear()

    mock_ig = MagicMock()
    item = {
        "item_id": "q1",
        "asset_ids": ["a1"],
        "format": "reel",
        "caption": "test",
        "hashtags": [],
        "idempotency_key": "k1",
    }

    with patch("app.instagram.poster.get_instagram_client", return_value=mock_ig):
        with patch("app.instagram.poster.GalleryQueueStore") as mock_queue_cls:
            mock_queue_cls.return_value.list_due.return_value = [item]
            with patch("app.instagram.poster._resolve_media_path", return_value=tmp_path / "v.mp4"):
                (tmp_path / "v.mp4").write_bytes(b"x")
                from app.instagram.poster import post_due

                results = post_due(limit=1)

    assert results[0]["ok"] is True
    assert results[0]["dry_run"] is True


def test_web_reels_filter():
    from types import SimpleNamespace

    from app.instagram.web_reels import _filter_reels, _is_reel_media

    reel = SimpleNamespace(product_type="clips", media_type=1)
    video = SimpleNamespace(product_type="feed", media_type=2)
    photo = SimpleNamespace(product_type="feed", media_type=1)

    assert _is_reel_media(reel) is True
    assert _is_reel_media(video) is True
    assert _is_reel_media(photo) is False
    assert len(_filter_reels([photo, reel, video], 2)) == 2
