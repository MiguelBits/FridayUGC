"""Smoke tests that run with the mock LLM provider — no GPU, no network."""

from __future__ import annotations

import os

os.environ.setdefault("FRIDAY_LLM_PROVIDER", "mock")
os.environ.setdefault("FRIDAY_API_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.ugc import safety  # noqa: E402

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-token"}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_required():
    r = client.post("/ugc/caption", json={"context": "gym reel"})
    assert r.status_code == 401


def test_agent_step_opens_instagram_when_not_foreground():
    body = {
        "session_id": "s1",
        "goal": "Scroll Instagram feed",
        "step": 0,
        "screen": {"app": "com.android.launcher", "elements": []},
        "history": [],
    }
    r = client.post("/agent/step", json=body, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["action"] == "open_app"


def test_agent_step_scrolls_when_instagram_open():
    body = {
        "session_id": "s1",
        "goal": "Scroll Instagram feed",
        "step": 1,
        "screen": {
            "app": "com.instagram.android",
            "elements": [{"id": 0, "role": "scrollable", "scrollable": True}],
        },
        "history": ["open_app"],
    }
    r = client.post("/agent/step", json=body, headers=AUTH)
    assert r.status_code == 200
    assert r.json()["action"] == "scroll"


def test_read_only_blocks_like():
    body = {
        "session_id": "s1",
        "goal": "FORCE_LIKE_ACTION on gym posts",
        "step": 2,
        "mode": "read_only",
        "screen": {
            "app": "com.instagram.android",
            "elements": [{"id": 0, "role": "button", "text": "Like"}],
        },
        "history": ["open_app", "scroll"],
    }
    r = client.post("/agent/step", json=body, headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["action"] == "swipe"
    assert "read_only" in data["reason"].lower()


def test_post_action_is_approval_gated():
    # Real-account mutations must be in the server-enforced approval set.
    from app.config import get_settings

    gated = get_settings().approval_action_set
    for action in ("post", "comment", "dm", "follow"):
        assert action in gated


def test_caption_endpoint():
    r = client.post("/ugc/caption", json={"context": "dressing room black dress", "cta": 1}, headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()["caption"]) > 0


def test_safety_visual_swaps():
    out = safety.sanitize_visual("tight bodycon with cleavage and sheer mesh")
    assert "bodycon" not in out.lower()
    assert "cleavage" not in out.lower()
    assert "sheer" not in out.lower()


def test_safety_dialogue_swaps():
    assert "good dog" in safety.sanitize_dialogue("good boy, keep watching").lower()


def test_gallery_list():
    r = client.get("/gallery", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["unposted"] >= 1


def test_gallery_analyze_vision():
    r = client.post("/gallery/analyze", json={"force": True}, headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["analyzed"] >= 1
    first = data["assets"][0]
    assert first["vision_summary"]
    assert first["vibe"]


def test_curate_from_gallery():
    r = client.post(
        "/ugc/curate",
        json={"days_ahead": 7, "max_posts_per_day": 2, "include_bio_update": True},
        headers=AUTH,
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["posting_queue"]) >= 1
    assert data["posting_queue"][0]["approval_required"] is True
    assert "strategy_notes" in data


def test_voice_speak_disabled_by_default():
    r = client.post("/voice/speak", json={"text": "Scrolling the feed now."}, headers=AUTH)
    assert r.status_code == 204


def test_voice_speak_returns_wav_when_enabled(monkeypatch):
    monkeypatch.setenv("FRIDAY_VOICE_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post("/voice/speak", json={"text": "Scrolling the feed now."}, headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
    assert len(r.content) > 44  # WAV header + frames
    get_settings.cache_clear()


def test_inbox_evaluate_selective():
    body = {
        "messages": [
            {"message_id": "a1", "author": "fan1", "text": "Where is that dress from?", "channel": "dm"},
            {"message_id": "a2", "author": "fan1", "text": "hey", "channel": "dm"},
            {"message_id": "a3", "author": "fan2", "text": "🔥", "channel": "comment", "post_id": "p1"},
        ],
        "draft_if_reply": True,
    }
    r = client.post("/inbox/evaluate", json=body, headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert len(data["decisions"]) == 3
    actions = {d["action"] for d in data["decisions"]}
    assert "skip" in actions or "defer" in actions


def test_ugc_routine_reels_comment_likes():
    r = client.post(
        "/ugc/routine",
        json={"routine": "reels_comment_likes", "duration_minutes": 30, "mode": "full"},
        headers=AUTH,
    )
    assert r.status_code == 200
    data = r.json()
    assert "reels_max" in data["goal"].lower() or "each reel" in data["goal"].lower()
    assert data["session_context"]["comment_likes_max"] == 50
    assert data["session_context"]["reels_max"] == 10
    assert data["session_context"]["phase"] == "reels_comment_likes"


def test_ugc_routine_full_session():
    r = client.post(
        "/ugc/routine",
        json={"routine": "full_session", "duration_minutes": 25, "mode": "full"},
        headers=AUTH,
    )
    assert r.status_code == 200
    data = r.json()
    assert "reels" in data["goal"].lower()
    assert data["session_context"]["likes_max"] >= 1
    assert len(data["checklist"]) >= 5


def test_inbox_record_and_cap(tmp_path, monkeypatch):
    ledger = tmp_path / "inbox_ledger.json"
    monkeypatch.setenv("FRIDAY_INBOX_LEDGER_PATH", str(ledger))
    from app.config import get_settings

    get_settings.cache_clear()

    r1 = client.post(
        "/inbox/record",
        json={
            "message_id": "r1",
            "author": "testuser_cap",
            "channel": "dm",
            "text_sent": "Maybe.",
        },
        headers=AUTH,
    )
    assert r1.status_code == 200
    assert r1.json()["replies_today_for_user"] == 1

    r2 = client.post(
        "/inbox/record",
        json={
            "message_id": "r2",
            "author": "testuser_cap",
            "channel": "dm",
            "text_sent": "Still thinking.",
        },
        headers=AUTH,
    )
    assert r2.status_code == 200
    assert r2.json()["replies_today_for_user"] == 2

    r = client.post(
        "/inbox/evaluate",
        json={
            "messages": [
                {"message_id": "x9", "author": "testuser_cap", "text": "hello again", "channel": "dm"},
            ],
        },
        headers=AUTH,
    )
    decision = r.json()["decisions"][0]
    assert decision["action"] == "skip"
    assert "daily_cap" in decision["reason"]


def test_safety_audit_flags_device_wording():
    warnings = safety.audit("she holds an iPhone in hand")
    assert any("device" in w for w in warnings)


def test_agent_step_records_run_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("FRIDAY_RUNS_DATA_PATH", str(tmp_path))
    from app.config import get_settings

    get_settings.cache_clear()

    body = {
        "session_id": "trace-test-1",
        "goal": "Scroll Instagram feed",
        "step": 0,
        "screen": {"app": "com.android.launcher", "elements": []},
        "history": [],
    }
    r = client.post("/agent/step", json=body, headers=AUTH)
    assert r.status_code == 200

    run = client.get("/runs/trace-test-1", headers=AUTH)
    assert run.status_code == 200
    data = run.json()
    assert data["session_id"] == "trace-test-1"
    assert len(data["steps"]) == 1
    assert data["steps"][0]["action"] == "open_app"
    assert data["steps"][0]["latency_ms"] >= 0

    metrics = client.get("/runs/metrics", headers=AUTH)
    assert metrics.status_code == 200
    assert metrics.json()["steps_total"] >= 1


def test_health_includes_model_ready():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["model_ready"] is True
    assert "model_detail" in data
