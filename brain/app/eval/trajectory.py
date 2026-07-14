"""Trajectory-style eval helpers inspired by langchain-ai/agentevals (no dependency).

Supports strict, subset, and superset matching for agent action steps — useful in
pytest fixtures and CI regression without LangSmith.
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class TrajectoryMatchMode(str, Enum):
    STRICT = "strict"
    SUBSET = "subset"
    SUPERSET = "superset"


def score_action_step(
    actual: str,
    expected: str | list[str] | None,
    *,
    mode: TrajectoryMatchMode = TrajectoryMatchMode.STRICT,
) -> bool:
    """Return True when *actual* satisfies *expected* under *mode*."""
    if expected is None:
        return True
    if isinstance(expected, str):
        expected_list = [expected]
    else:
        expected_list = list(expected)

    if mode == TrajectoryMatchMode.STRICT:
        return len(expected_list) == 1 and actual == expected_list[0]

    if mode == TrajectoryMatchMode.SUBSET:
        # Actual must be one of the allowed expected actions.
        return actual in expected_list

    if mode == TrajectoryMatchMode.SUPERSET:
        # Expected list must include actual (reference trajectory is minimal).
        return actual in expected_list

    return False


def match_trajectory(
    actual_steps: list[str],
    expected_steps: list[str],
    *,
    mode: TrajectoryMatchMode = TrajectoryMatchMode.STRICT,
) -> tuple[bool, list[str]]:
    """Compare two action-name sequences. Returns (ok, error_messages)."""
    errors: list[str] = []

    if mode == TrajectoryMatchMode.STRICT:
        if actual_steps != expected_steps:
            errors.append(f"expected trajectory {expected_steps!r}, got {actual_steps!r}")
        return (not errors, errors)

    if mode == TrajectoryMatchMode.SUBSET:
        for step in actual_steps:
            if step not in expected_steps:
                errors.append(f"unexpected step {step!r} not in allowed {expected_steps!r}")
        return (not errors, errors)

    if mode == TrajectoryMatchMode.SUPERSET:
        missing = [s for s in expected_steps if s not in actual_steps]
        if missing:
            errors.append(f"reference trajectory missing steps: {missing!r}")
        return (not errors, errors)

    return (False, [f"unknown mode {mode!r}"])


def check_step_expectations(
    *,
    action: str,
    reason: str = "",
    approval_required: bool = False,
    needs_screenshot: bool = False,
    params: dict[str, Any] | None = None,
    guard_triggered: bool = False,
    expect: dict[str, Any],
) -> list[str]:
    """Shared assertion helper for agent eval fixtures."""
    errors: list[str] = []
    params = params or {}

    if "action" in expect and action != expect["action"]:
        errors.append(f"expected action={expect['action']!r}, got {action!r}")

    if "action_in" in expect and action not in expect["action_in"]:
        errors.append(f"expected action in {expect['action_in']!r}, got {action!r}")

    if "action_mode" in expect and "action_in" in expect:
        mode = TrajectoryMatchMode(expect["action_mode"])
        if not score_action_step(action, expect["action_in"], mode=mode):
            errors.append(f"action {action!r} failed {mode.value} match")

    if "forbidden_actions" in expect and action in expect["forbidden_actions"]:
        errors.append(f"forbidden action {action!r}")

    if expect.get("approval_required") is True and not approval_required:
        errors.append("expected approval_required=True")

    if expect.get("needs_screenshot") is True and not needs_screenshot:
        errors.append("expected needs_screenshot=True")

    if expect.get("guard_triggered") is True and not guard_triggered:
        errors.append("expected guard_triggered=True")

    if "reason_contains" in expect:
        needle = expect["reason_contains"].lower()
        if needle not in reason.lower():
            errors.append(f"expected reason to contain {needle!r}")

    if "params_package" in expect:
        pkg = params.get("package", "")
        if pkg != expect["params_package"]:
            errors.append(f"expected params.package={expect['params_package']!r}, got {pkg!r}")

    if "params_tab" in expect:
        tab = params.get("tab", "")
        if tab != expect["params_tab"]:
            errors.append(f"expected params.tab={expect['params_tab']!r}, got {tab!r}")

    return errors
