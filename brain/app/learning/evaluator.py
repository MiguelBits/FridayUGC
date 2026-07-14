from __future__ import annotations

from datetime import datetime, timezone

from .schemas import EvalFailureCase, EvalReport
from .store import LearningStore


class LearningEvaluator:
    """Replay recent failed/unverified steps and estimate fixability."""

    def __init__(self, store: LearningStore | None = None) -> None:
        self.store = store or LearningStore()

    def run(self, limit: int = 50) -> EvalReport:
        rows = self.store.recent_failures(limit=limit)
        cases: list[EvalFailureCase] = []
        would_fix = 0
        for row in rows:
            action = row.get("action", "")
            verified = row.get("verified", "")
            executor_ok = bool(row.get("executor_ok"))
            change_score = float(row.get("change_score") or 0.0)
            reason = row.get("error") or verified or "unverified"
            case = EvalFailureCase(
                session_id=row.get("session_id", ""),
                step=int(row.get("step") or 0),
                action=action,
                goal=row.get("goal", ""),
                screen_fp_before=row.get("screen_fp_before", ""),
                reason=str(reason),
            )
            cases.append(case)
            if self._would_fix(action, executor_ok, change_score, verified):
                would_fix += 1
        reviewed = len(cases)
        pass_rate = (would_fix / reviewed) if reviewed else 1.0
        report = EvalReport(
            ran_at=datetime.now(timezone.utc).isoformat(),
            cases_reviewed=reviewed,
            would_fix=would_fix,
            pass_rate=round(pass_rate, 4),
            failures=cases[:20],
            notes=(
                f"Reviewed {reviewed} recent failures. "
                f"{would_fix} likely recoverable with memory/vision/retry."
            ),
        )
        self.store.save_eval_report(report)
        return report

    @staticmethod
    def _would_fix(action: str, executor_ok: bool, change_score: float, verified: str) -> bool:
        if verified == "verified":
            return True
        if not executor_ok and action in {"tap", "navigate", "like_comment"}:
            return True
        if change_score < 0.05 and action in {"swipe", "scroll", "tap"}:
            return True
        if verified == "unverified" and change_score >= 0.1:
            return True
        return False
