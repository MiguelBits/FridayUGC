"""Gallery queue and record-post tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_API_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def queue_db(tmp_path, monkeypatch):
    db = tmp_path / "queue.db"
    monkeypatch.setenv("FRIDAY_GALLERY_QUEUE_PATH", str(db))
    from app.config import get_settings

    get_settings.cache_clear()
    return db


def test_gallery_scan_and_record_post(queue_db):
    client = TestClient(app)
    scan = client.post("/gallery/scan", headers=AUTH)
    assert scan.status_code == 200
    assert scan.json()["scanned"] >= 1

    assets = client.get("/gallery", headers=AUTH).json()["assets"]
    asset_id = assets[0]["id"]
    enqueue = client.post(
        "/gallery/queue",
        json={
            "asset_ids": [asset_id],
            "format": "reel",
            "caption": "test caption",
            "hashtags": ["#test"],
            "scheduled_at": "2000-01-01T12:00:00+00:00",
        },
        headers=AUTH,
    )
    assert enqueue.status_code == 200

    sync = client.get("/gallery/sync", headers=AUTH)
    assert sync.status_code == 200
    assert len(sync.json()["due_items"]) >= 1

    record = client.post(
        "/gallery/record-post",
        json={
            "asset_ids": [asset_id],
            "idempotency_key": "post-test-1",
            "format": "reel",
        },
        headers=AUTH,
    )
    assert record.status_code == 200
    assert record.json()["ok"] is True

    dup = client.post(
        "/gallery/record-post",
        json={
            "asset_ids": [asset_id],
            "idempotency_key": "post-test-1",
            "format": "reel",
        },
        headers=AUTH,
    )
    assert dup.json()["deduplicated"] is True
