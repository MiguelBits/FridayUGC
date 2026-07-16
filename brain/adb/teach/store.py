"""Teach episode + skill aggregation store (disk JSON, no Y-offset probing)."""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

VALID_SKILLS = frozenset(
    {
        "open_comments",
        "like_comment",
        "scroll_comments",
        "close_comments",
        "next_reel",
        "full_loop",
    }
)

# Skills with a working interactive record path.
IMPLEMENTED_SKILLS = frozenset({"open_comments", "like_comment", "full_loop"})

VALID_LABELS = frozenset({"ok", "fail", "ad", "wrong_sheet", "trap"})

SKILL_ANCHORS: dict[str, str] = {
    "open_comments": "comments_icon",
    "like_comment": "comment_heart",
    "scroll_comments": "comments_sheet",
    "close_comments": "close_comments",
    "next_reel": "reels_swipe",
    "full_loop": "full_loop",
}

# Skills that sync median coords into LearningStore.device_memory.
_MEMORY_SYNC_SKILLS = frozenset({"open_comments", "like_comment"})

MIN_OK_FOR_MOTOR = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "teach"


def _median_int(values: list[int]) -> int:
    if not values:
        return 0
    return int(round(statistics.median(values)))


def _median_float(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def skill_filename(skill: str, device_id: str) -> str:
    safe = (device_id or "default").replace(":", "_").replace("/", "_")
    return f"{skill}__{safe}.json"


class TeachStore:
    """Persist human demos under data/teach/ and aggregate successful anchors."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        learning_db_path: Path | str | None = None,
    ) -> None:
        self.root = Path(root) if root else _default_root()
        self.episodes_dir = self.root / "episodes"
        self.shots_dir = self.root / "shots"
        self.skills_dir = self.root / "skills"
        self.replay_dir = self.root / "replay"
        for d in (self.episodes_dir, self.shots_dir, self.skills_dir, self.replay_dir):
            d.mkdir(parents=True, exist_ok=True)
        self._learning_db_path = Path(learning_db_path) if learning_db_path else None

    def episode_path(self, episode_id: str) -> Path:
        return self.episodes_dir / f"{episode_id}.json"

    def save_episode(self, episode: dict[str, Any], *, aggregate: bool = True) -> Path:
        skill = str(episode.get("skill") or "")
        label = str(episode.get("label") or "")
        if skill not in VALID_SKILLS:
            raise ValueError(f"invalid skill: {skill}")
        if label not in VALID_LABELS:
            raise ValueError(f"invalid label: {label}")

        episode = dict(episode)
        episode.setdefault("created_at", _utc_now())
        episode_id = str(episode["episode_id"])
        path = self.episode_path(episode_id)
        path.write_text(json.dumps(episode, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        if aggregate and label == "ok":
            device_id = str(episode.get("device_id") or "default")
            self.aggregate_skill(skill, device_id)
        return path

    def load_episode(self, episode_id: str) -> dict[str, Any] | None:
        path = self.episode_path(episode_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_episodes(
        self,
        skill: str | None = None,
        device_id: str | None = None,
        label: str | None = None,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for path in sorted(self.episodes_dir.glob("*.json")):
            try:
                ep = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if skill and ep.get("skill") != skill:
                continue
            if device_id and ep.get("device_id") != device_id:
                continue
            if label and ep.get("label") != label:
                continue
            out.append(ep)
        return out

    def get_skill(self, skill: str, device_id: str) -> dict[str, Any] | None:
        path = self.skills_dir / skill_filename(skill, device_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def get_skill_coord(
        self,
        skill: str,
        device_id: str,
        *,
        min_ok: int = MIN_OK_FOR_MOTOR,
    ) -> tuple[int, int] | None:
        data = self.get_skill(skill, device_id)
        if not data:
            return None
        if int(data.get("n_ok") or 0) < min_ok:
            return None
        x = int(data.get("x") or 0)
        y = int(data.get("y") or 0)
        if x <= 0 or y <= 0:
            return None
        return x, y

    def aggregate_skill(self, skill: str, device_id: str) -> dict[str, Any] | None:
        """Rebuild skill from ok episodes with tap coords. Sync LearningStore on success."""
        ok_eps = [
            ep
            for ep in self.list_episodes(skill=skill, device_id=device_id, label="ok")
            if int(ep.get("tap_x") or 0) > 0 and int(ep.get("tap_y") or 0) > 0
        ]
        if not ok_eps:
            path = self.skills_dir / skill_filename(skill, device_id)
            if path.is_file():
                path.unlink()
            return None

        xs = [int(ep["tap_x"]) for ep in ok_eps]
        ys = [int(ep["tap_y"]) for ep in ok_eps]
        x_fracs = [float(ep.get("tap_x_frac") or 0.0) for ep in ok_eps if ep.get("tap_x_frac") is not None]
        y_fracs = [float(ep.get("tap_y_frac") or 0.0) for ep in ok_eps if ep.get("tap_y_frac") is not None]
        # Backfill fracs from absolute when missing.
        for ep in ok_eps:
            w = int(ep.get("screen_width") or 0)
            h = int(ep.get("screen_height") or 0)
            if w > 0 and ep.get("tap_x_frac") is None:
                x_fracs.append(int(ep["tap_x"]) / w)
            if h > 0 and ep.get("tap_y_frac") is None:
                y_fracs.append(int(ep["tap_y"]) / h)

        w0 = int(ok_eps[-1].get("screen_width") or 0)
        h0 = int(ok_eps[-1].get("screen_height") or 0)
        skill_data: dict[str, Any] = {
            "skill_id": skill,
            "anchor": SKILL_ANCHORS.get(skill, skill),
            "device_id": device_id,
            "x": _median_int(xs),
            "y": _median_int(ys),
            "x_frac": round(_median_float(x_fracs), 4) if x_fracs else 0.0,
            "y_frac": round(_median_float(y_fracs), 4) if y_fracs else 0.0,
            "screen_width": w0,
            "screen_height": h0,
            "n_ok": len(ok_eps),
            "episode_ids": [str(ep["episode_id"]) for ep in ok_eps],
            "updated_at": _utc_now(),
        }
        path = self.skills_dir / skill_filename(skill, device_id)
        path.write_text(json.dumps(skill_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self._sync_learning_memory(skill_data)
        return skill_data

    def _sync_learning_memory(self, skill_data: dict[str, Any]) -> None:
        """Push only successful taught coords into LearningStore.device_memory."""
        skill = str(skill_data.get("skill_id") or "")
        if skill not in _MEMORY_SYNC_SKILLS:
            return
        anchor = SKILL_ANCHORS.get(skill, skill)
        device_id = str(skill_data.get("device_id") or "")
        x = int(skill_data.get("x") or 0)
        y = int(skill_data.get("y") or 0)
        n_ok = int(skill_data.get("n_ok") or 0)
        if not device_id or x <= 0 or y <= 0 or n_ok <= 0:
            return
        try:
            from app.learning.schemas import DeviceMemoryEntry
            from app.learning.store import LearningStore

            store = LearningStore(path=str(self._learning_db_path) if self._learning_db_path else None)
            store.sync_memory(
                device_id,
                [
                    DeviceMemoryEntry(
                        device_id=device_id,
                        ui_key=anchor,
                        x=x,
                        y=y,
                        resource_hint="teach",
                        success_count=n_ok,
                        fail_count=0,
                        last_verified_at=_utc_now(),
                    )
                ],
            )
        except Exception:
            # Teach store must work even if learning DB import fails offline.
            pass


def suggest_label_from_texts(
    after_texts: list[str],
    before_texts: list[str] | None = None,
    *,
    skill: str = "open_comments",
) -> Optional[str]:
    """Heuristic label suggestion for the human to confirm (never auto-commits)."""
    from .classify import (
        score_close_comments,
        score_like_comment,
        score_open_comments,
        score_scroll_comments,
    )

    if skill == "like_comment":
        scored = score_like_comment(after_texts or [], before_texts=before_texts)
    elif skill == "scroll_comments":
        scored = score_scroll_comments(after_texts or [], before_texts=before_texts)
    elif skill in {"close_comments", "next_reel"}:
        scored = score_close_comments(after_texts or [], before_texts=before_texts)
    else:
        scored = score_open_comments(after_texts or [], before_texts=before_texts)
    return str(scored.get("label_guess") or "") or None
