"""Record success/fail tap coords so the brain stops re-guessing bad icons."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def record_anchor_outcome(
    device_id: str,
    ui_key: str,
    *,
    x: int,
    y: int,
    success: bool,
    ig_version: str = "",
    screen_width: int = 0,
    screen_height: int = 0,
    screenshot_b64: str | None = None,
) -> None:
    """Bump device memory / grounding exemplars after a judged open_comments attempt."""
    if not device_id or not ui_key or x <= 0 or y <= 0:
        return
    try:
        from ...learning.schemas import VerifiedStepRecord
        from ...learning.store import LearningStore

        store = LearningStore()
        verified = "verified" if success else "unverified"
        step = VerifiedStepRecord(
            session_id="flow-memory",
            device_id=device_id,
            step=0,
            goal=f"flow record {ui_key}",
            action="tap",
            executor_ok=True,
            verified=verified,  # type: ignore[arg-type]
            change_score=1.0 if success else 0.0,
            params={
                "x": x,
                "y": y,
                "ui_key": ui_key,
                "screen_width": screen_width,
                "screen_height": screen_height,
            },
            screenshot_b64=screenshot_b64 if success else None,
            anchor=ui_key,
            ig_version=ig_version,
        )
        store.record_steps([step])
        if not success:
            # Explicit fail bump when record_steps only saves exemplars on verified.
            with store._conn() as conn:  # noqa: SLF001
                row = conn.execute(
                    "SELECT success_count, fail_count FROM device_memory WHERE device_id=? AND ui_key=?",
                    (device_id, ui_key),
                ).fetchone()
                if row:
                    conn.execute(
                        "UPDATE device_memory SET fail_count=fail_count+1 WHERE device_id=? AND ui_key=?",
                        (device_id, ui_key),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO device_memory(
                            device_id, ui_key, x, y, resource_hint, success_count, fail_count,
                            last_verified_at, ig_version
                        ) VALUES (?, ?, ?, ?, '', 0, 1, datetime('now'), ?)
                        """,
                        (device_id, ui_key, x, y, ig_version),
                    )
        logger.info(
            "flow memory %s %s at (%s,%s) device=%s",
            "OK" if success else "FAIL",
            ui_key,
            x,
            y,
            device_id[:12],
        )
    except Exception as exc:
        logger.warning("record_anchor_outcome failed: %s", exc)


def next_comments_y_frac(
    ctx: dict[str, Any],
    *,
    screen_width: int = 1080,
    screen_height: int = 2400,
) -> float:
    """Pick Y fraction for deterministic comments tap; rotate offsets after failures."""
    from .defs import COMMENTS_ICON_Y_OFFSETS, comments_y_frac_for_screen

    base = comments_y_frac_for_screen(screen_width, screen_height)
    try:
        idx = int(ctx.get("comments_icon_offset_idx", 0))
    except (TypeError, ValueError):
        idx = 0
    offsets = COMMENTS_ICON_Y_OFFSETS
    idx = max(0, idx) % len(offsets)
    return base + offsets[idx]


def bump_comments_offset(ctx: dict[str, Any]) -> None:
    try:
        idx = int(ctx.get("comments_icon_offset_idx", 0))
    except (TypeError, ValueError):
        idx = 0
    ctx["comments_icon_offset_idx"] = idx + 1
