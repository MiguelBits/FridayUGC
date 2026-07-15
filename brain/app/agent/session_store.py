"""Authoritative session state for /agent/tick — budgets, phases, retry counters."""

from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CTX: dict[str, Any] = {
    "likes_used": 0,
    "likes_max": 25,
    "story_likes_used": 0,
    "story_likes_max": 12,
    "reels_scrolled": 0,
    "reels_max": 35,
    "comments_used": 0,
    "comments_max": 8,
    "comment_likes_used": 0,
    "comment_likes_max": 50,
    "comment_likes_this_reel": 0,
    "comment_likes_per_reel": 5,
    "dms_used": 0,
    "dms_max": 10,
    "follows_used": 0,
    "follows_max": 3,
    "saves_used": 0,
    "saves_max": 5,
    "phase": "reels",
    "reels_tab_opened": 0,
    "reels_entry_attempts": 0,
    "comments_sheet_open": 0,
    "comment_likes_phase": "on_reels",
    "ready_for_next_reel": 0,
    "comment_likes_since_scroll": 0,
    "comment_sheet_scrolls": 0,
}

ANCHOR_RETRY: dict[str, int] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self, path: str | None = None) -> None:
        default = Path(__file__).resolve().parents[2] / "data" / "sessions" / "tick_sessions.db"
        self.path = Path(path or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self._memory: dict[str, dict[str, Any]] = {}

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tick_sessions (
                    session_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    history_json TEXT NOT NULL,
                    anchor_retries_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def load(self, session_id: str, goal: str = "", device_id: str = "", seed: dict | None = None) -> dict[str, Any]:
        if session_id in self._memory:
            return deepcopy(self._memory[session_id])
        with self._conn() as conn:
            row = conn.execute(
                "SELECT context_json, history_json, anchor_retries_json FROM tick_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row:
            ctx = {**DEFAULT_CTX, **json.loads(row["context_json"])}
            self._memory[session_id] = {
                "context": ctx,
                "history": json.loads(row["history_json"]),
                "anchor_retries": json.loads(row["anchor_retries_json"]),
            }
            return deepcopy(self._memory[session_id])
        ctx = deepcopy(DEFAULT_CTX)
        if seed:
            ctx.update(seed)
        if goal and "comment" in goal.lower() and "reel" in goal.lower():
            ctx["phase"] = "reels_comment_likes"
        self._memory[session_id] = {"context": ctx, "history": [], "anchor_retries": {}}
        self._persist(session_id, goal, device_id)
        return deepcopy(self._memory[session_id])

    def _persist(self, session_id: str, goal: str, device_id: str) -> None:
        data = self._memory.get(session_id)
        if not data:
            return
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO tick_sessions(session_id, goal, device_id, context_json, history_json,
                    anchor_retries_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    context_json=excluded.context_json,
                    history_json=excluded.history_json,
                    anchor_retries_json=excluded.anchor_retries_json,
                    updated_at=excluded.updated_at
                """,
                (
                    session_id,
                    goal,
                    device_id,
                    json.dumps(data["context"]),
                    json.dumps(data["history"]),
                    json.dumps(data["anchor_retries"]),
                    _utc_now(),
                ),
            )

    def save(self, session_id: str, goal: str, device_id: str) -> None:
        self._persist(session_id, goal, device_id)

    def context(self, session_id: str) -> dict[str, Any]:
        return deepcopy(self._memory[session_id]["context"])

    def anchor_retries(self, session_id: str) -> dict[str, int]:
        return deepcopy(self._memory[session_id]["anchor_retries"])

    def bump_anchor_retry(self, session_id: str, anchor: str) -> int:
        retries = self._memory[session_id]["anchor_retries"]
        retries[anchor] = retries.get(anchor, 0) + 1
        return retries[anchor]

    def reset_anchor_retry(self, session_id: str, anchor: str) -> None:
        self._memory[session_id]["anchor_retries"][anchor] = 0

    def append_history(self, session_id: str, entry: str) -> None:
        hist = self._memory[session_id]["history"]
        hist.append(entry)
        if len(hist) > 80:
            del hist[:-80]
