"""Intent protocol tests."""

from __future__ import annotations

from app.agent.intents import INTENT_NAMES, INTENT_SPEC
from app.agent.actions import ActionName
import typing


def test_intent_in_action_name_literal():
    names = set(typing.get_args(ActionName))
    assert "intent" in names


def test_intent_names_catalog():
    assert "enter_reels" in INTENT_NAMES
    assert "next_reel" in INTENT_NAMES
    assert "open_comments" in INTENT_NAMES


def test_intent_spec_documents_enter_reels():
    assert "enter_reels" in INTENT_SPEC
    assert "device memory" in INTENT_SPEC.lower() or "memory" in INTENT_SPEC.lower()
