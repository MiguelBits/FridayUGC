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
from app.agent.router import _guard_info  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.llm import ChatMessage, get_llm  # noqa: E402
from app.persona import get_persona  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "agent_scenarios"


def _load_scenarios() -> list[tuple[str, dict[str, Any]]]:
    scenarios: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(FIXTURES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios.append((data.get("name", path.stem), data))
    return scenarios


def _check_expect(resp, expect: dict[str, Any], guard_triggered: bool) -> list[str]:
    errors: list[str] = []

    if "action" in expect and resp.action != expect["action"]:
        errors.append(f"expected action={expect['action']!r}, got {resp.action!r}")

    if "action_in" in expect and resp.action not in expect["action_in"]:
        errors.append(f"expected action in {expect['action_in']!r}, got {resp.action!r}")

    if expect.get("approval_required") is True and not resp.approval_required:
        errors.append("expected approval_required=True")

    if expect.get("guard_triggered") is True and not guard_triggered:
        errors.append("expected guard_triggered=True")

    if "reason_contains" in expect:
        needle = expect["reason_contains"].lower()
        if needle not in (resp.reason or "").lower():
            errors.append(f"expected reason to contain {needle!r}")

    if expect.get("approval_if_action") == resp.action and not resp.approval_required:
        errors.append(f"expected approval_required for action {resp.action!r}")

    if "params_package" in expect:
        pkg = (resp.params or {}).get("package", "")
        if pkg != expect["params_package"]:
            errors.append(f"expected params.package={expect['params_package']!r}, got {pkg!r}")

    return errors


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
    return _check_expect(resp, expect, guard_triggered)


@pytest.mark.parametrize("name,data", _load_scenarios())
def test_agent_scenario(name: str, data: dict[str, Any]) -> None:
    req = StepRequest.model_validate(data["request"])
    expect = data.get("expect", {})
    errors = asyncio.run(_run_scenario(req, expect))
    assert not errors, f"{name}: " + "; ".join(errors)


def test_agent_eval_all_pass() -> None:
    """Portfolio summary: every fixture scenario must pass on mock provider."""
    passed = 0
    for name, data in _load_scenarios():
        req = StepRequest.model_validate(data["request"])
        errors = asyncio.run(_run_scenario(req, data.get("expect", {})))
        if not errors:
            passed += 1
        else:
            pytest.fail(f"{name}: " + "; ".join(errors))
    assert passed == len(_load_scenarios())
