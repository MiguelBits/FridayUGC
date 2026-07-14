"""Tests for inbox reply policy — caps and selective answering."""

from __future__ import annotations

from app.inbox.policy import evaluate_one, is_low_effort
from app.inbox.schemas import IncomingMessage
from app.inbox.store import InboxStore


def test_low_effort_detection():
    assert is_low_effort("hey")
    assert is_low_effort("Hi!!")
    assert not is_low_effort("Where did you get that dress?")


def test_daily_cap_per_user(monkeypatch, tmp_path):
    from datetime import date

    from app.config import Settings, get_settings

    today = date.today().isoformat()
    ledger_file = tmp_path / "ledger.json"
    ledger_file.write_text(
        f'{{"replies": ['
        f'{{"user":"jane","channel":"dm","message_id":"1","thread_id":"","date":"{today}",'
        f'"at":"2026-07-09T10:00:00+00:00","text_preview":"hi"}},'
        f'{{"user":"jane","channel":"dm","message_id":"2","thread_id":"","date":"{today}",'
        f'"at":"2026-07-09T14:00:00+00:00","text_preview":"ok"}}'
        f"]}}",
        encoding="utf-8",
    )
    get_settings.cache_clear()

    class TestSettings(Settings):
        inbox_ledger_path: str = str(ledger_file)

    monkeypatch.setattr("app.inbox.policy.get_settings", lambda: TestSettings())
    monkeypatch.setattr("app.inbox.store.get_settings", lambda: TestSettings())

    msg = IncomingMessage(message_id="m3", author="jane", text="you there?", channel="dm")
    decision = evaluate_one(msg, InboxStore())
    assert decision.action == "skip"
    assert "daily_cap" in decision.reason

    get_settings.cache_clear()
