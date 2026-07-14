"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_operator_db(tmp_path, monkeypatch):
    """Each test gets a fresh SQLite operator store."""
    db = tmp_path / "operator.db"
    queue = tmp_path / "queue.db"
    monkeypatch.setenv("FRIDAY_OPERATOR_DB_PATH", str(db))
    monkeypatch.setenv("FRIDAY_GALLERY_QUEUE_PATH", str(queue))
    monkeypatch.setenv("FRIDAY_LEARNING_DB_PATH", str(tmp_path / "learning.db"))
    monkeypatch.setenv("FRIDAY_LLM_PROVIDER", "mock")
    monkeypatch.setenv("FRIDAY_API_TOKEN", "test-token")
    from app.config import get_settings

    get_settings.cache_clear()
    yield
