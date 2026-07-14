"""Bench task fixture validation (MobileAgentBench-style)."""

from __future__ import annotations

from app.eval.bench import BenchTask, check_success, load_bench_tasks


def test_bench_tasks_load():
    tasks = load_bench_tasks()
    assert len(tasks) >= 3
    assert all(isinstance(t, BenchTask) for t in tasks)


def test_bench_success_inbox():
    task = next(t for t in load_bench_tasks() if t.name == "reach_inbox")
    ok, errors = check_success(
        task,
        screen_type="inbox",
        app="com.instagram.android",
        element_count=12,
        actions=["open_app", "navigate", "wait"],
    )
    assert ok, errors


def test_bench_success_fails_wrong_screen():
    task = next(t for t in load_bench_tasks() if t.name == "open_comments_on_reel")
    ok, errors = check_success(
        task,
        screen_type="home_feed",
        app="com.instagram.android",
        element_count=20,
        actions=["open_app"],
    )
    assert not ok
    assert any("screen_type" in e for e in errors)
