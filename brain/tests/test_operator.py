"""Operator subsystem tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_API_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.operator.store import OperatorStore  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


@pytest.fixture()
def operator_db(tmp_path, monkeypatch):
    db = tmp_path / "operator.db"
    monkeypatch.setenv("FRIDAY_OPERATOR_DB_PATH", str(db))
    from app.config import get_settings

    get_settings.cache_clear()
    return db


def test_operator_day_plan_and_claim(operator_db):
    client = TestClient(app)
    plan = client.post(
        "/operator/day-plan",
        json={"timezone": "Etc/UTC", "mode": "full", "comment_likes_target": 20},
        headers=AUTH,
    )
    assert plan.status_code == 200
    tasks = plan.json()["tasks"]
    assert len(tasks) >= 3

    claim = client.post(
        "/operator/tasks/claim",
        json={"device_id": "phone-1"},
        headers=AUTH,
    )
    assert claim.status_code == 200
    body = claim.json()
    assert body["task"] is not None
    assert body["task"]["status"] in {"claimed", "pending", "running"}


def test_operator_kill_switch(operator_db):
    client = TestClient(app)
    killed = client.post("/operator/kill", json={"reason": "test stop"}, headers=AUTH)
    assert killed.status_code == 200
    assert killed.json()["enabled"] is False

    step = client.post(
        "/agent/step",
        json={
            "session_id": "paused-1",
            "goal": "Scroll Instagram",
            "step": 0,
            "screen": {"app": "com.instagram.android", "elements": []},
        },
        headers=AUTH,
    )
    assert step.status_code == 200
    assert step.json()["action"] == "fail"

    resumed = client.post("/operator/resume", headers=AUTH)
    assert resumed.status_code == 200
    assert resumed.json()["enabled"] is True


def test_step_dedup(operator_db):
    client = TestClient(app)
    body = {
        "session_id": "dedup-1",
        "goal": "Scroll Instagram feed",
        "step": 0,
        "screen": {"app": "com.android.launcher", "elements": []},
    }
    first = client.post("/agent/step", json=body, headers=AUTH).json()
    second = client.post("/agent/step", json=body, headers=AUTH).json()
    assert first["action"] == second["action"]


def test_daily_quota_blocks_like(operator_db):
    store = OperatorStore(str(operator_db))
    daily = store.get_daily()
    caps = store.get_caps()
    daily.likes = caps.likes
    store.save_daily(daily)

    client = TestClient(app)
    step = client.post(
        "/agent/step",
        json={
            "session_id": "quota-like-unique",
            "goal": "FORCE_LIKE_ACTION on gym posts",
            "step": 3,
            "mode": "full",
            "screen": {
                "app": "com.instagram.android",
                "elements": [{"id": 0, "text": "Like", "clickable": True}],
            },
            "history": ["open_app", "scroll", "scroll"],
        },
        headers=AUTH,
    )
    assert step.status_code == 200
    data = step.json()
    assert data["done"] is True or "daily_like_cap" in data.get("reason", "")
