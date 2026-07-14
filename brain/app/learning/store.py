from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import get_settings
from .schemas import (
    DeviceMemoryEntry,
    EvalFailureCase,
    EvalReport,
    LearningMetrics,
    NovelPlanRecord,
    VerifiedStepRecord,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningStore:
    def __init__(self, path: str | None = None) -> None:
        settings = get_settings()
        default = Path(__file__).resolve().parents[2] / "data" / "learning" / "trajectories.db"
        self.path = Path(path or getattr(settings, "learning_db_path", "") or default)
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
                CREATE TABLE IF NOT EXISTS verified_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    step INTEGER NOT NULL,
                    goal TEXT NOT NULL,
                    action TEXT NOT NULL,
                    executor_ok INTEGER NOT NULL,
                    verified TEXT NOT NULL,
                    change_score REAL NOT NULL,
                    screen_fp_before TEXT NOT NULL,
                    screen_fp_after TEXT NOT NULL,
                    foreground_app_before TEXT NOT NULL,
                    foreground_app_after TEXT NOT NULL,
                    element_count_before INTEGER NOT NULL,
                    element_count_after INTEGER NOT NULL,
                    error TEXT,
                    ig_version TEXT NOT NULL,
                    params TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_verified_device ON verified_steps(device_id);
                CREATE INDEX IF NOT EXISTS idx_verified_failed ON verified_steps(verified);
                CREATE TABLE IF NOT EXISTS device_memory (
                    device_id TEXT NOT NULL,
                    ui_key TEXT NOT NULL,
                    x INTEGER NOT NULL,
                    y INTEGER NOT NULL,
                    resource_hint TEXT NOT NULL,
                    success_count INTEGER NOT NULL,
                    fail_count INTEGER NOT NULL,
                    last_verified_at TEXT NOT NULL,
                    ig_version TEXT NOT NULL,
                    PRIMARY KEY (device_id, ui_key)
                );
                CREATE TABLE IF NOT EXISTS eval_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ran_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS novel_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    signature TEXT NOT NULL UNIQUE,
                    action_sequence TEXT NOT NULL,
                    step_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_novel_device ON novel_plans(device_id);
                """
            )

    def record_steps(self, steps: list[VerifiedStepRecord]) -> tuple[int, int]:
        failures = 0
        with self._conn() as conn:
            for step in steps:
                conn.execute(
                    """
                    INSERT INTO verified_steps(
                        session_id, device_id, step, goal, action, executor_ok, verified,
                        change_score, screen_fp_before, screen_fp_after,
                        foreground_app_before, foreground_app_after,
                        element_count_before, element_count_after, error, ig_version, params, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        step.session_id,
                        step.device_id,
                        step.step,
                        step.goal,
                        step.action,
                        int(step.executor_ok),
                        step.verified,
                        step.change_score,
                        step.screen_fp_before,
                        step.screen_fp_after,
                        step.foreground_app_before,
                        step.foreground_app_after,
                        step.element_count_before,
                        step.element_count_after,
                        step.error,
                        step.ig_version,
                        json.dumps(step.params),
                        _utc_now(),
                    ),
                )
                if step.verified in {"failed", "unverified"} or not step.executor_ok:
                    failures += 1
                if step.verified == "verified" and step.executor_ok:
                    self._bump_memory(conn, step)
        return len(steps), failures

    def record_novel_plans(self, steps: list[VerifiedStepRecord]) -> list[NovelPlanRecord]:
        """Persist first-seen verified action sequences (Genie novel-plan pattern)."""
        verified = [s for s in steps if s.verified == "verified" and s.executor_ok]
        if len(verified) < 3:
            return []
        actions = [s.action for s in verified]
        signature = "|".join(actions)
        goal = verified[0].goal
        device_id = verified[0].device_id
        created: list[NovelPlanRecord] = []
        with self._conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO novel_plans(device_id, goal, signature, action_sequence, step_count, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (device_id, goal, signature, json.dumps(actions), len(actions), _utc_now()),
                )
                created.append(
                    NovelPlanRecord(
                        device_id=device_id,
                        goal=goal,
                        signature=signature,
                        action_sequence=actions,
                        step_count=len(actions),
                        created_at=_utc_now(),
                    )
                )
            except sqlite3.IntegrityError:
                pass
        return created

    def list_novel_plans(self, device_id: str | None = None, limit: int = 20) -> list[NovelPlanRecord]:
        with self._conn() as conn:
            if device_id:
                rows = conn.execute(
                    "SELECT * FROM novel_plans WHERE device_id = ? ORDER BY id DESC LIMIT ?",
                    (device_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM novel_plans ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        out: list[NovelPlanRecord] = []
        for row in rows:
            try:
                seq = json.loads(row["action_sequence"])
            except json.JSONDecodeError:
                seq = []
            out.append(
                NovelPlanRecord(
                    device_id=row["device_id"],
                    goal=row["goal"],
                    signature=row["signature"],
                    action_sequence=seq if isinstance(seq, list) else [],
                    step_count=int(row["step_count"]),
                    created_at=row["created_at"],
                )
            )
        return out

    def novel_plan_hints(self, device_id: str, limit: int = 5) -> str:
        plans = self.list_novel_plans(device_id, limit=limit)
        if not plans:
            return ""
        lines = ["NOVEL_PLANS (verified sequences learned on this device):"]
        for p in plans:
            preview = " → ".join(p.action_sequence[:6])
            if len(p.action_sequence) > 6:
                preview += " → …"
            lines.append(f"  - {p.goal[:80]!r}: {preview}")
        return "\n".join(lines) + "\n"

    def _bump_memory(self, conn: sqlite3.Connection, step: VerifiedStepRecord) -> None:
        ui_key = _ui_key_for_action(step.action, step.params)
        if not ui_key:
            return
        x = int(step.params.get("x") or 0)
        y = int(step.params.get("y") or 0)
        target_id = step.params.get("target_id")
        resource_hint = str(target_id) if target_id is not None else ""
        conn.execute(
            """
            INSERT INTO device_memory(
                device_id, ui_key, x, y, resource_hint, success_count, fail_count,
                last_verified_at, ig_version
            ) VALUES (?, ?, ?, ?, ?, 1, 0, ?, ?)
            ON CONFLICT(device_id, ui_key) DO UPDATE SET
                x = CASE WHEN excluded.x > 0 THEN excluded.x ELSE device_memory.x END,
                y = CASE WHEN excluded.y > 0 THEN excluded.y ELSE device_memory.y END,
                resource_hint = CASE WHEN excluded.resource_hint != '' THEN excluded.resource_hint ELSE device_memory.resource_hint END,
                success_count = device_memory.success_count + 1,
                last_verified_at = excluded.last_verified_at,
                ig_version = excluded.ig_version
            """,
            (step.device_id, ui_key, x, y, resource_hint, _utc_now(), step.ig_version),
        )

    def sync_memory(self, device_id: str, entries: list[DeviceMemoryEntry]) -> int:
        with self._conn() as conn:
            for entry in entries:
                conn.execute(
                    """
                    INSERT INTO device_memory(
                        device_id, ui_key, x, y, resource_hint, success_count, fail_count,
                        last_verified_at, ig_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, ui_key) DO UPDATE SET
                        x = excluded.x,
                        y = excluded.y,
                        resource_hint = excluded.resource_hint,
                        success_count = MAX(device_memory.success_count, excluded.success_count),
                        fail_count = MAX(device_memory.fail_count, excluded.fail_count),
                        last_verified_at = excluded.last_verified_at,
                        ig_version = excluded.ig_version
                    """,
                    (
                        device_id,
                        entry.ui_key,
                        entry.x,
                        entry.y,
                        entry.resource_hint,
                        entry.success_count,
                        entry.fail_count,
                        entry.last_verified_at or _utc_now(),
                        entry.ig_version,
                    ),
                )
        return len(entries)

    def get_memory(self, device_id: str) -> list[DeviceMemoryEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM device_memory WHERE device_id = ? ORDER BY success_count DESC",
                (device_id,),
            ).fetchall()
        return [
            DeviceMemoryEntry(
                device_id=row["device_id"],
                ui_key=row["ui_key"],
                x=row["x"],
                y=row["y"],
                resource_hint=row["resource_hint"],
                success_count=row["success_count"],
                fail_count=row["fail_count"],
                last_verified_at=row["last_verified_at"],
                ig_version=row["ig_version"],
            )
            for row in rows
        ]

    def memory_hints_for_prompt(self, device_id: str, limit: int = 8) -> str:
        entries = self.get_memory(device_id)[:limit]
        if not entries:
            return ""
        lines = ["DEVICE_MEMORY (learned on this phone — prefer these):"]
        for e in entries:
            coord = f"tap x={e.x}, y={e.y}" if e.x > 0 and e.y > 0 else f"target_id={e.resource_hint}"
            lines.append(f"  - {e.ui_key}: {coord} (ok={e.success_count}, fail={e.fail_count})")
        return "\n".join(lines) + "\n"

    def recent_failures(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM verified_steps
                WHERE verified IN ('failed', 'unverified') OR executor_ok = 0
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_eval_report(self, report: EvalReport) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO eval_reports(ran_at, payload) VALUES (?, ?)",
                (report.ran_at, report.model_dump_json()),
            )

    def latest_eval_report(self) -> EvalReport | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM eval_reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return EvalReport.model_validate_json(row["payload"])

    def metrics(self) -> LearningMetrics:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) AS c FROM verified_steps").fetchone()["c"]
            verified = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_steps WHERE verified = 'verified'"
            ).fetchone()["c"]
            failed = conn.execute(
                "SELECT COUNT(*) AS c FROM verified_steps WHERE verified IN ('failed', 'unverified') OR executor_ok = 0"
            ).fetchone()["c"]
            memory = conn.execute("SELECT COUNT(*) AS c FROM device_memory").fetchone()["c"]
        rate = (verified / total) if total else 0.0
        last_eval = self.latest_eval_report()
        return LearningMetrics(
            trajectories_total=total,
            verified_steps=verified,
            failed_steps=failed,
            verification_rate=round(rate, 4),
            memory_entries=memory,
            last_eval_at=last_eval.ran_at if last_eval else None,
            last_eval_pass_rate=last_eval.pass_rate if last_eval else None,
        )


def _ui_key_for_action(action: str, params: dict[str, Any]) -> str | None:
    if action in {"tap", "like", "like_comment", "like_story", "save", "follow"}:
        tab = params.get("tab")
        if tab:
            return f"nav_{tab}"
        if action == "like_comment":
            return "comments_icon"
        return f"action_{action}"
    if action == "navigate":
        tab = str(params.get("tab", "")).lower()
        return f"nav_{tab}" if tab else "navigate"
    if action == "swipe":
        return "reels_swipe"
    return None
