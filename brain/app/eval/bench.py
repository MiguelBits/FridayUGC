"""MobileAgentBench-style task definitions for eval harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "bench_tasks"


class BenchSuccessCondition(BaseModel):
    """Flexible success check — mirrors MobileAgentBench final-state idea."""

    screen_type: str | None = None
    foreground_app_contains: str | None = None
    min_element_count: int | None = None
    action_trajectory_subset: list[str] = Field(default_factory=list)


class BenchTask(BaseModel):
    name: str
    goal: str
    difficulty: str = "medium"
    max_steps: int = 20
    mode: str = "read_only"
    success: BenchSuccessCondition = Field(default_factory=BenchSuccessCondition)
    notes: str = ""


def load_bench_tasks() -> list[BenchTask]:
    if not FIXTURES_DIR.is_dir():
        return []
    tasks: list[BenchTask] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        tasks.append(BenchTask.model_validate(data))
    return tasks


def check_success(task: BenchTask, *, screen_type: str, app: str, element_count: int, actions: list[str]) -> tuple[bool, list[str]]:
    """Return (passed, errors) for a simulated or recorded session end state."""
    cond = task.success
    errors: list[str] = []
    if cond.screen_type and screen_type != cond.screen_type:
        errors.append(f"expected screen_type={cond.screen_type}, got {screen_type}")
    if cond.foreground_app_contains and cond.foreground_app_contains.lower() not in app.lower():
        errors.append(f"expected app containing {cond.foreground_app_contains!r}, got {app!r}")
    if cond.min_element_count is not None and element_count < cond.min_element_count:
        errors.append(f"expected element_count>={cond.min_element_count}, got {element_count}")
    if cond.action_trajectory_subset:
        missing = [a for a in cond.action_trajectory_subset if a not in actions]
        if missing:
            errors.append(f"trajectory missing actions: {missing}")
    return len(errors) == 0, errors


def task_to_scenario_stub(task: BenchTask) -> dict[str, Any]:
    """Map a bench task to a minimal agent_scenarios-compatible stub for CI."""
    return {
        "name": task.name,
        "bench": True,
        "request": {
            "session_id": "bench",
            "goal": task.goal,
            "step": 0,
            "mode": task.mode,
            "screen": {"app": "com.instagram.android", "activity": "", "elements": []},
            "history": [],
        },
        "expect": {},
    }
