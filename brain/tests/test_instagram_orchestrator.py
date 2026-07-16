"""Tests for Instagram orchestrator + reels comment likes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.instagram.budget import EngagementBudget
from app.instagram.engagement import reels_comment_likes_session
from app.instagram.orchestrator import InstagramOrchestrator, ENABLED_KINDS
from app.operator.schemas import DayPlanRequest, TaskRecord
from app.operator.service import OperatorService
from app.operator.store import OperatorStore


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_enabled_kinds_reels_only():
    assert "reels_comment_likes" in ENABLED_KINDS
    assert "post_reel" not in ENABLED_KINDS


def test_budget_blocks_when_cap_hit(tmp_path, monkeypatch):
    db = tmp_path / "op.db"
    monkeypatch.setenv("FRIDAY_OPERATOR_DB_PATH", str(db))
    get_settings.cache_clear()
    store = OperatorStore(str(db))
    daily = store.get_daily()
    caps = store.get_caps()
    daily.comment_likes = caps.comment_likes
    store.save_daily(daily)

    budget = EngagementBudget(store)
    assert budget.block_reason() == "daily_comment_like_cap"


def test_reels_session_dry_run(monkeypatch):
    monkeypatch.setenv("FRIDAY_IG_READ_ONLY", "true")
    get_settings.cache_clear()

    mock_media = MagicMock(pk="111")
    mock_comment = MagicMock(pk=999, has_liked=False)

    mock_cl = MagicMock()
    mock_cl.explore_reels.return_value = [mock_media]
    mock_cl.media_comments.return_value = [mock_comment, mock_comment]

    mock_ig = MagicMock()
    mock_ig.client.return_value = mock_cl
    mock_ig.human_pause = MagicMock()

    with patch("app.instagram.engagement.get_instagram_client", return_value=mock_ig):
        result = reels_comment_likes_session(reels_max=1, read_only=True, ig=mock_ig)

    assert result["ok"] is True
    assert result["reels_processed"] == 1
    assert result["comment_likes"] >= 1
    mock_cl.comment_like.assert_not_called()


def test_reels_only_day_plan(tmp_path, monkeypatch):
    db = tmp_path / "op.db"
    monkeypatch.setenv("FRIDAY_OPERATOR_DB_PATH", str(db))
    get_settings.cache_clear()

    orch = InstagramOrchestrator(OperatorService(OperatorStore(str(db))))
    out = orch.plan_reels_day(mode="read_only", sessions=3)
    assert out["tasks"] == 3
    tasks = orch.operator.list_tasks()
    assert all(t.kind == "reels_comment_likes" for t in tasks)


def test_orchestrator_skips_unimplemented_kind(tmp_path, monkeypatch):
    db = tmp_path / "op.db"
    monkeypatch.setenv("FRIDAY_OPERATOR_DB_PATH", str(db))
    get_settings.cache_clear()

    store = OperatorStore(str(db))
    store.replace_tasks_for_day(
        "2099-01-01",
        [
            TaskRecord(
                task_id="t1",
                kind="inbox",
                goal="inbox",
                scheduled_at="2099-01-01T00:00:00+00:00",
                mode="read_only",
            )
        ],
    )
    with store._conn() as conn:
        conn.execute(
            "UPDATE tasks SET scheduled_at = datetime('now', '-1 minute') WHERE task_id = 't1'"
        )

    orch = InstagramOrchestrator(OperatorService(store))
    result = orch.claim_and_run()
    assert result is not None
    assert result.get("skipped") is True
