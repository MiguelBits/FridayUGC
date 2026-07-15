"""Learning loop: verified trajectories, device memory, eval."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.learning.schemas import DeviceMemoryEntry, DeviceMemorySyncRequest, TrajectoryBatchRequest, VerifiedStepRecord
from app.learning.service import LearningService
from app.main import app

AUTH = {"Authorization": "Bearer test-token"}


def _step(**kwargs) -> VerifiedStepRecord:
    base = dict(
        session_id="s1",
        device_id="phone-a",
        step=1,
        goal="Like comments on reels",
        action="tap",
        executor_ok=True,
        verified="verified",
        change_score=0.4,
        screen_fp_before="aaa",
        screen_fp_after="bbb",
        params={"x": 120, "y": 800, "target_id": "like_btn"},
    )
    base.update(kwargs)
    return VerifiedStepRecord(**base)


def test_record_trajectory_and_memory_bump():
    svc = LearningService()
    resp = svc.record_trajectory(
        TrajectoryBatchRequest(device_id="phone-a", steps=[_step()])
    )
    assert resp.accepted == 1
    assert resp.failures_recorded == 0
    memory = svc.get_memory("phone-a")
    assert len(memory.entries) >= 1
    assert memory.entries[0].x == 120


def test_like_comment_ui_key_maps_to_comment_heart():
    from app.learning.store import _ui_key_for_action

    assert _ui_key_for_action("like_comment", {}) == "comment_heart"


def test_memory_hints_in_prompt():
    svc = LearningService()
    svc.record_trajectory(TrajectoryBatchRequest(device_id="phone-b", steps=[_step(device_id="phone-b")]))
    hints = svc.memory_hints("phone-b")
    assert "DEVICE_MEMORY" in hints
    assert "action_tap" in hints or "120" in hints


def test_eval_reports_failures():
    svc = LearningService()
    svc.record_trajectory(
        TrajectoryBatchRequest(
            device_id="phone-a",
            steps=[_step(verified="unverified", change_score=0.01, executor_ok=True)],
        )
    )
    report = svc.run_eval(limit=10)
    assert report.cases_reviewed >= 1
    assert 0.0 <= report.pass_rate <= 1.0
    assert svc.latest_eval() is not None


def test_grounding_example_stored_for_vision_anchor():
    svc = LearningService()
    svc.record_trajectory(
        TrajectoryBatchRequest(
            device_id="phone-v",
            steps=[
                _step(
                    device_id="phone-v",
                    anchor="comments_icon",
                    params={"x": 990, "y": 1250, "ui_key": "comments_icon", "screen_width": "1080", "screen_height": "2400"},
                )
            ],
        )
    )
    examples = svc.grounding_examples("comments_icon", device_id="phone-v")
    assert len(examples) == 1
    assert examples[0].x == 990
    export = svc.export_grounding_dataset(anchor="comments_icon", limit=10)
    assert export[0]["anchor"] == "comments_icon"


def test_learning_api_endpoints():
    client = TestClient(app)
    batch = TrajectoryBatchRequest(device_id="api-phone", steps=[_step(device_id="api-phone", session_id="api-s1")])
    r = client.post("/learning/trajectory", json=batch.model_dump(), headers=AUTH)
    assert r.status_code == 200
    assert r.json()["accepted"] == 1

    r = client.get("/learning/memory/api-phone", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["device_id"] == "api-phone"

    sync = DeviceMemorySyncRequest(
        device_id="api-phone",
        entries=[
            DeviceMemoryEntry(
                device_id="api-phone",
                ui_key="nav_reels",
                x=50,
                y=900,
                success_count=3,
            )
        ],
    )
    r = client.post("/learning/memory", json=sync.model_dump(), headers=AUTH)
    assert r.status_code == 200

    r = client.get("/learning/metrics", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["trajectories_total"] >= 1

    r = client.post("/learning/eval?limit=5", headers=AUTH)
    assert r.status_code == 200

    r = client.get("/learning/eval/latest", headers=AUTH)
    assert r.status_code == 200


def test_novel_plan_recorded_on_verified_sequence():
    svc = LearningService()
    steps = [
        _step(step=i, action=a, device_id="novel-phone", session_id="novel-s1")
        for i, a in enumerate(["open_app", "navigate", "intent"], start=1)
    ]
    svc.record_trajectory(TrajectoryBatchRequest(device_id="novel-phone", steps=steps))
    plans = svc.list_novel_plans("novel-phone")
    assert len(plans) == 1
    assert plans[0].action_sequence == ["open_app", "navigate", "intent"]
    hints = svc.novel_plan_hints("novel-phone")
    assert "NOVEL_PLANS" in hints


def test_vision_on_ambiguous_without_screenshot():
    from app.agent.actions import Screen, ScreenElement, StepRequest
    from app.agent.router import decide_legacy
    import asyncio

    req = StepRequest(
        session_id="ambig",
        goal="Scroll reels",
        step=0,
        screen=Screen(
            app="com.instagram.android",
            elements=[ScreenElement(id=i, text=f"el{i}") for i in range(5)],
        ),
        device_id="phone-a",
    )
    resp = asyncio.run(decide_legacy(req))
    assert resp.needs_screenshot is True
    assert resp.action == "wait"
