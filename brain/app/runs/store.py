from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config import get_settings
from .schemas import RunMetrics, SessionRun, StepTrace

_RUNS_DIR = Path(__file__).resolve().parents[2] / "data" / "runs"


def _runs_dir() -> Path:
    s = get_settings()
    if s.runs_data_path.strip():
        return Path(s.runs_data_path)
    return _RUNS_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    def _path(self, session_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in session_id)
        return _runs_dir() / f"{safe}.json"

    def load(self, session_id: str) -> SessionRun | None:
        path = self._path(session_id)
        if not path.is_file():
            return None
        return SessionRun.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, run: SessionRun) -> None:
        path = self._path(run.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    def record_step(
        self,
        *,
        session_id: str,
        goal: str,
        trace: StepTrace,
        terminal: bool = False,
        failed: bool = False,
    ) -> SessionRun:
        run = self.load(session_id)
        now = _utc_now()
        if run is None:
            run = SessionRun(
                session_id=session_id,
                goal=goal,
                status="active",
                started_at=now,
                updated_at=now,
            )
        if not run.goal and goal:
            run.goal = goal
        run.steps.append(trace)
        run.updated_at = now
        if failed:
            run.status = "failed"
        elif terminal:
            run.status = "done"
        self.save(run)
        return run

    def list_recent(self, limit: int = 20) -> list[SessionRun]:
        root = _runs_dir()
        if not root.is_dir():
            return []
        paths = sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        runs: list[SessionRun] = []
        for path in paths[:limit]:
            try:
                runs.append(SessionRun.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return runs

    def metrics(self) -> RunMetrics:
        root = _runs_dir()
        if not root.is_dir():
            return RunMetrics(
                sessions_total=0,
                sessions_done=0,
                sessions_failed=0,
                sessions_active=0,
                steps_total=0,
                guard_interventions=0,
                avg_latency_ms=0.0,
                completion_rate=0.0,
            )

        runs = self.list_recent(limit=500)
        steps_total = sum(r.total_steps for r in runs)
        guard_total = sum(r.guard_interventions for r in runs)
        latencies = [s.latency_ms for r in runs for s in r.steps]
        done = sum(1 for r in runs if r.status == "done")
        failed = sum(1 for r in runs if r.status == "failed")
        active = sum(1 for r in runs if r.status == "active")
        total = len(runs)
        completion = (done / total) if total else 0.0
        avg_lat = (sum(latencies) / len(latencies)) if latencies else 0.0

        return RunMetrics(
            sessions_total=total,
            sessions_done=done,
            sessions_failed=failed,
            sessions_active=active,
            steps_total=steps_total,
            guard_interventions=guard_total,
            avg_latency_ms=round(avg_lat, 2),
            completion_rate=round(completion, 4),
        )
