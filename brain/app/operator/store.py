from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_settings
from .schemas import (
    CheckpointRequest,
    DailyCaps,
    DailyQuota,
    OperatorStatus,
    TaskRecord,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperatorStore:
    def __init__(self, path: str | None = None) -> None:
        settings = get_settings()
        default = Path(__file__).resolve().parents[2] / "data" / "operator" / "state.db"
        self.path = Path(path or settings.operator_db_path or default)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS operator_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_ledger (
                    date TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    scheduled_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    session_context TEXT NOT NULL,
                    max_steps INTEGER NOT NULL,
                    claimed_by TEXT,
                    session_id TEXT,
                    result_summary TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoints (
                    resume_token TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS step_dedup (
                    session_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (session_id, step)
                );
                """
            )

    def _meta_get(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM operator_meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def _meta_set(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO operator_meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def is_enabled(self) -> bool:
        return self._meta_get("enabled", "true").lower() != "false"

    def kill(self, reason: str) -> None:
        self._meta_set("enabled", "false")
        self._meta_set("kill_reason", reason)

    def resume_operator(self) -> None:
        self._meta_set("enabled", "true")
        self._meta_set("kill_reason", "")

    def get_caps(self) -> DailyCaps:
        raw = self._meta_get("daily_caps")
        if raw:
            return DailyCaps.model_validate_json(raw)
        return DailyCaps()

    def set_caps(self, caps: DailyCaps) -> None:
        self._meta_set("daily_caps", caps.model_dump_json())

    def get_daily(self, day: str | None = None) -> DailyQuota:
        day = day or date.today().isoformat()
        with self._conn() as conn:
            row = conn.execute("SELECT payload FROM daily_ledger WHERE date = ?", (day,)).fetchone()
        if row:
            return DailyQuota.model_validate_json(row["payload"])
        return DailyQuota(date=day)

    def save_daily(self, quota: DailyQuota) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO daily_ledger(date, payload) VALUES(?, ?) "
                "ON CONFLICT(date) DO UPDATE SET payload = excluded.payload",
                (quota.date, quota.model_dump_json()),
            )

    def status(self) -> OperatorStatus:
        daily = self.get_daily()
        caps = self.get_caps()
        with self._conn() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS c FROM tasks WHERE status IN ('pending', 'claimed', 'running')"
            ).fetchone()["c"]
        return OperatorStatus(
            enabled=self.is_enabled(),
            kill_reason=self._meta_get("kill_reason") or None,
            fsm_state=self._meta_get("fsm_state", "IDLE"),
            daily=daily,
            caps=caps,
            pending_tasks=pending,
            active_session_id=self._meta_get("active_session_id") or None,
        )

    def replace_tasks_for_day(self, day: str, tasks: list[TaskRecord]) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM tasks WHERE scheduled_at LIKE ?", (f"{day}%",))
            for task in tasks:
                conn.execute(
                    """
                    INSERT INTO tasks(
                        task_id, kind, goal, scheduled_at, status, mode, session_context,
                        max_steps, claimed_by, session_id, result_summary, error, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.kind,
                        task.goal,
                        task.scheduled_at,
                        task.status,
                        task.mode,
                        json.dumps(task.session_context),
                        task.max_steps,
                        task.claimed_by,
                        task.session_id,
                        task.result_summary,
                        task.error,
                        _utc_now(),
                    ),
                )

    def list_tasks(self, day: str | None = None) -> list[TaskRecord]:
        day = day or date.today().isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE scheduled_at LIKE ? ORDER BY scheduled_at",
                (f"{day}%",),
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def claim_next_task(self, device_id: str, after: str | None = None) -> TaskRecord | None:
        now = _utc_now()
        with self._conn() as conn:
            query = (
                "SELECT * FROM tasks WHERE status = 'pending' AND scheduled_at <= ? "
            )
            params: list[Any] = [now]
            if after:
                query += "AND scheduled_at > ? "
                params.append(after)
            query += "ORDER BY scheduled_at LIMIT 1"
            row = conn.execute(query, params).fetchone()
            if not row:
                return None
            session_id = str(uuid.uuid4())
            conn.execute(
                "UPDATE tasks SET status = 'claimed', claimed_by = ?, session_id = ? WHERE task_id = ?",
                (device_id, session_id, row["task_id"]),
            )
            for key, value in (
                ("active_session_id", session_id),
                ("fsm_state", "RUNNING"),
            ):
                conn.execute(
                    "INSERT INTO operator_meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (row["task_id"],)).fetchone()
        return self._row_to_task(updated)

    def complete_task(
        self,
        task_id: str,
        *,
        ok: bool,
        summary: str,
        error: str | None,
        session_context: dict[str, Any],
    ) -> None:
        status = "completed" if ok else "failed"
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE tasks SET status = ?, result_summary = ?, error = ?, session_context = ?
                WHERE task_id = ?
                """,
                (status, summary, error, json.dumps(session_context), task_id),
            )
            for key, value in (("active_session_id", ""), ("fsm_state", "IDLE")):
                conn.execute(
                    "INSERT INTO operator_meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

    def save_checkpoint(self, req: CheckpointRequest) -> str:
        token = str(uuid.uuid4())
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints(resume_token, session_id, payload, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (token, req.session_id, req.model_dump_json(), _utc_now()),
            )
        return token

    def load_checkpoint(self, token: str) -> CheckpointRequest | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM checkpoints WHERE resume_token = ?", (token,)
            ).fetchone()
        if not row:
            return None
        return CheckpointRequest.model_validate_json(row["payload"])

    def get_idempotent(self, key: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT payload FROM idempotency WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        return json.loads(row["payload"])

    def put_idempotent(self, key: str, payload: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO idempotency(key, payload, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(payload), _utc_now()),
            )

    def get_step_response(self, session_id: str, step: int) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM step_dedup WHERE session_id = ? AND step = ?",
                (session_id, step),
            ).fetchone()
        return json.loads(row["payload"]) if row else None

    def put_step_response(self, session_id: str, step: int, payload: dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO step_dedup(session_id, step, payload) VALUES (?, ?, ?)",
                (session_id, step, json.dumps(payload)),
            )

    def apply_engagement(self, action: str, ctx: dict[str, Any]) -> DailyQuota:
        daily = self.get_daily()
        if action == "like":
            daily.likes += 1
        elif action == "like_story":
            daily.story_likes += 1
        elif action == "like_comment":
            daily.comment_likes += 1
        elif action == "comment":
            daily.comments += 1
        elif action == "dm":
            daily.dms += 1
        elif action == "follow":
            daily.follows += 1
        elif action == "post":
            daily.posts += 1
        elif action == "story":
            daily.stories += 1
        elif action == "swipe" and ctx.get("phase") in {"reels", "reels_comment_likes"}:
            daily.reels_scrolled += 1
        self.save_daily(daily)
        return daily

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            kind=row["kind"],
            goal=row["goal"],
            scheduled_at=row["scheduled_at"],
            status=row["status"],
            mode=row["mode"],
            session_context=json.loads(row["session_context"] or "{}"),
            max_steps=row["max_steps"],
            claimed_by=row["claimed_by"],
            session_id=row["session_id"],
            result_summary=row["result_summary"],
            error=row["error"],
        )
