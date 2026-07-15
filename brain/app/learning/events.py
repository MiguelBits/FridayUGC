"""Non-blocking agent event log (Genie EventLogger pattern)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("friday.agent.events")


class AgentEventLogger:
    """Lightweight structured events for learning + debugging."""

    def emit(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "payload": payload or {},
        }
        logger.info("agent_event %s", json.dumps(entry, default=str))

    def trajectory_batch(self, device_id: str, accepted: int, failures: int) -> None:
        self.emit(
            "trajectory_batch",
            {"device_id": device_id, "accepted": accepted, "failures": failures},
        )

    def novel_plan(self, device_id: str, signature: str, goal: str) -> None:
        self.emit(
            "novel_plan",
            {"device_id": device_id, "signature": signature, "goal": goal},
        )


event_logger = AgentEventLogger()
