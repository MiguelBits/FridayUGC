from __future__ import annotations

from app.eval.trajectory import TrajectoryMatchMode, match_trajectory, score_action_step


def test_score_action_step_strict():
    assert score_action_step("scroll", "scroll", mode=TrajectoryMatchMode.STRICT)
    assert not score_action_step("scroll", "tap", mode=TrajectoryMatchMode.STRICT)


def test_score_action_step_subset():
    allowed = ["navigate", "intent", "wait"]
    assert score_action_step("navigate", allowed, mode=TrajectoryMatchMode.SUBSET)
    assert not score_action_step("like", allowed, mode=TrajectoryMatchMode.SUBSET)


def test_match_trajectory_superset():
    ok, errors = match_trajectory(
        ["open_app", "navigate", "scroll"],
        ["open_app", "scroll"],
        mode=TrajectoryMatchMode.SUPERSET,
    )
    assert ok
    assert errors == []


def test_match_trajectory_strict_mismatch():
    ok, errors = match_trajectory(
        ["open_app", "scroll"],
        ["open_app", "navigate"],
        mode=TrajectoryMatchMode.STRICT,
    )
    assert not ok
    assert errors
