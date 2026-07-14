from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_API_TOKEN", "test-token")

from app.agent.actions import StepRequest  # noqa: E402
from app.agent.prompt import apply_guards, build_step_user_prompt, parse_step_json, response_from_json  # noqa: E402
from app.agent.router import _guard_info, decide_legacy  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.eval.trajectory import check_step_expectations  # noqa: E402
from app.llm import ChatMessage, get_llm  # noqa: E402
from app.persona import get_persona  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent_scenarios"


def _load_scenarios(*, routed: bool | None = None) -> list[tuple[str, dict[str, Any]]]:
    scenarios: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        is_route = bool(data.get("route"))
        if routed is True and not is_route:
            continue
        if routed is False and is_route:
            continue
        scenarios.append((data.get("name", path.stem), data))
    return scenarios


async def _run_scenario(req: StepRequest, expect: dict[str, Any]) -> list[str]:
    settings = get_settings()
    persona = get_persona("lorena")
    llm = get_llm()
    user = build_step_user_prompt(req)
    raw = await llm.chat(
        [ChatMessage("system", persona.system_prompt), ChatMessage("user", user)],
        json_mode=True,
        temperature=settings.temperature,
        max_tokens=768,
    )
    parsed = parse_step_json(raw)
    resp_raw = response_from_json(parsed)
    resp = apply_guards(req, resp_raw)
    guard_triggered, _ = _guard_info(req, resp_raw, resp)
    return check_step_expectations(
        action=resp.action,
        reason=resp.reason or "",
        approval_required=resp.approval_required,
        needs_screenshot=resp.needs_screenshot,
        params=resp.params,
        guard_triggered=guard_triggered,
        expect=expect,
    )


async def _run_router_scenario(req: StepRequest, expect: dict[str, Any]) -> list[str]:
    resp = await decide_legacy(req)
    return check_step_expectations(
        action=resp.action,
        reason=resp.reason or "",
        approval_required=resp.approval_required,
        needs_screenshot=resp.needs_screenshot,
        params=resp.params,
        guard_triggered=False,
        expect=expect,
    )


@pytest.mark.parametrize("name,data", _load_scenarios(routed=False))
def test_agent_scenario(name: str, data: dict[str, Any]) -> None:
    req = StepRequest.model_validate(data["request"])
    expect = data.get("expect", {})
    errors = asyncio.run(_run_scenario(req, expect))
    assert not errors, f"{name}: " + "; ".join(errors)


@pytest.mark.parametrize("name,data", _load_scenarios(routed=True))
def test_agent_router_scenario(name: str, data: dict[str, Any]) -> None:
    req = StepRequest.model_validate(data["request"])
    expect = data.get("expect", {})
    errors = asyncio.run(_run_router_scenario(req, expect))
    assert not errors, f"{name}: " + "; ".join(errors)


def test_agent_eval_all_pass() -> None:
    """Portfolio summary: every LLM fixture scenario must pass on mock provider."""
    passed = 0
    for name, data in _load_scenarios(routed=False):
        req = StepRequest.model_validate(data["request"])
        errors = asyncio.run(_run_scenario(req, data.get("expect", {})))
        if not errors:
            passed += 1
        else:
            pytest.fail(f"{name}: " + "; ".join(errors))
    assert passed == len(_load_scenarios(routed=False))
