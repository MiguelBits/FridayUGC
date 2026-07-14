"""Tests for shared JSON extraction from LLM outputs."""

from __future__ import annotations

from app.llm.json_extract import extract_json_object, parse_model, repair_inline_action
from app.agent.actions import StepResponse


def test_extract_json_object_from_markdown_fence():
    raw = '```json\n{"action":"swipe","params":{"direction":"up"}}\n```'
    data = extract_json_object(raw)
    assert data["action"] == "swipe"
    assert data["params"]["direction"] == "up"


def test_repair_inline_action():
    name, params = repair_inline_action('swipe{"direction": "up"}')
    assert name == "swipe"
    assert params["direction"] == "up"


def test_parse_model_step_response():
    raw = '{"action":"tap","params":{"x":120,"y":400},"done":false}'
    model, warnings = parse_model(raw, StepResponse)
    assert model is not None
    assert model.action == "tap"
    assert model.params["x"] == 120
    assert not warnings


def test_parse_model_returns_fallback_on_garbage():
    model, warnings = parse_model("not json at all", StepResponse, fallback=StepResponse(action="wait"))
    assert model is not None
    assert model.action == "wait"
    assert warnings
