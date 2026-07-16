"""Teach mode: label → store → load skill; reject ad/trap as success."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from adb.teach.classify import score_open_comments
from adb.teach.coords import parse_coord_input
from adb.teach.store import TeachStore


def _ok_episode(device_id: str, x: int, y: int, w: int = 1440, h: int = 3216) -> dict:
    eid = str(uuid.uuid4())
    return {
        "episode_id": eid,
        "skill": "open_comments",
        "label": "ok",
        "device_id": device_id,
        "screen_width": w,
        "screen_height": h,
        "tap_x": x,
        "tap_y": y,
        "tap_x_frac": x / w,
        "tap_y_frac": y / h,
        "before_path": f"shots/{eid}_before.png",
        "after_path": f"shots/{eid}_after.png",
        "before_texts": [],
        "after_texts": ["Comentários"],
    }


def test_ok_episode_aggregates_median_and_syncs_memory(tmp_path: Path):
    learn_db = tmp_path / "learn.db"
    store = TeachStore(root=tmp_path / "teach", learning_db_path=learn_db)
    device = "phone-teach"

    store.save_episode(_ok_episode(device, 1300, 1600))
    store.save_episode(_ok_episode(device, 1320, 1680))
    store.save_episode(_ok_episode(device, 1340, 1700))

    skill = store.get_skill("open_comments", device)
    assert skill is not None
    assert skill["n_ok"] == 3
    assert skill["x"] == 1320
    assert skill["y"] == 1680
    assert skill["anchor"] == "comments_icon"

    coord = store.get_skill_coord("open_comments", device, min_ok=3)
    assert coord == (1320, 1680)

    from app.learning.store import LearningStore

    mem = LearningStore(path=str(learn_db)).get_memory(device)
    assert any(e.ui_key == "comments_icon" and e.x == 1320 and e.y == 1680 for e in mem)
    assert any(e.ui_key == "comments_icon" and e.fail_count == 0 for e in mem)


@pytest.mark.parametrize("label", ["ad", "trap", "wrong_sheet", "fail"])
def test_negative_labels_never_enter_skill(tmp_path: Path, label: str):
    learn_db = tmp_path / "learn.db"
    store = TeachStore(root=tmp_path / "teach", learning_db_path=learn_db)
    device = "phone-neg"
    eid = str(uuid.uuid4())
    ep = {
        "episode_id": eid,
        "skill": "open_comments",
        "label": label,
        "device_id": device,
        "screen_width": 1440,
        "screen_height": 3216,
        "tap_x": 1320,
        "tap_y": 1680,
        "tap_x_frac": 0.9,
        "tap_y_frac": 0.52,
        "before_path": f"shots/{eid}_before.png",
        "after_path": f"shots/{eid}_after.png",
        "before_texts": [],
        "after_texts": [],
    }
    store.save_episode(ep)
    assert store.get_skill("open_comments", device) is None
    assert store.get_skill_coord("open_comments", device) is None

    from app.learning.store import LearningStore

    mem = LearningStore(path=str(learn_db)).get_memory(device)
    assert not any(e.ui_key == "comments_icon" and e.success_count > 0 for e in mem)


def test_label_roundtrip(tmp_path: Path):
    store = TeachStore(root=tmp_path / "teach")
    ep = _ok_episode("dev1", 100, 200)
    store.save_episode(ep)
    loaded = store.load_episode(ep["episode_id"])
    assert loaded is not None
    assert loaded["label"] == "ok"
    assert loaded["skill"] == "open_comments"
    assert loaded["tap_x"] == 100


def test_score_open_comments_comments_ok():
    scored = score_open_comments(["Comentários", "Adicionar um comentário…"])
    assert scored["ok"] is True
    assert scored["label_guess"] == "ok"


def test_score_open_comments_rejects_cookie_trap():
    scored = score_open_comments(["Cookie settings", "Reject all", "Accept all"])
    assert scored["ok"] is False
    assert scored["label_guess"] == "trap"


def test_score_open_comments_rejects_share():
    scored = score_open_comments(["Repost", "Copy link", "Share to…"])
    assert scored["ok"] is False
    assert scored["label_guess"] == "wrong_sheet"


def test_parse_coord_percent_and_absolute():
    x, y, xf, yf = parse_coord_input("92% 52%", screen_width=1440, screen_height=3216)
    assert abs(xf - 0.92) < 1e-6
    assert abs(yf - 0.52) < 1e-6
    assert x == int(round(0.92 * 1440))
    assert y == int(round(0.52 * 3216))

    x2, y2, _, _ = parse_coord_input("1320,1680", screen_width=1440, screen_height=3216)
    assert (x2, y2) == (1320, 1680)


def test_motor_resolver_prefers_teach_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.agent import motor_resolver as mr

    learn_db = tmp_path / "learn.db"
    store = TeachStore(root=tmp_path / "teach", learning_db_path=learn_db)
    device = "phone-motor"
    for x, y in ((1300, 1600), (1320, 1680), (1340, 1700)):
        store.save_episode(_ok_episode(device, x, y))

    monkeypatch.setattr(mr, "_teach_coord", lambda device_id, ui_key: store.get_skill_coord("open_comments", device_id))
    assert mr._memory_coord(device, "comments_icon") == (1320, 1680)


def test_ask_label_enter_means_ok(monkeypatch: pytest.MonkeyPatch):
    from adb.teach import session as teach_session

    answers = iter([""])  # bare Enter
    monkeypatch.setattr(teach_session, "_prompt", lambda _msg: next(answers))
    assert teach_session._ask_label("fail") == "ok"


def test_ask_label_no_then_fail_reason(monkeypatch: pytest.MonkeyPatch):
    from adb.teach import session as teach_session

    answers = iter(["n", ""])  # no → Enter accepts suggested fail
    monkeypatch.setattr(teach_session, "_prompt", lambda _msg: next(answers))
    assert teach_session._ask_label("wrong_sheet") == "wrong_sheet"
