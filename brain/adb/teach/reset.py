"""Wipe all teach demos/skills and synced comments_icon memory."""

from __future__ import annotations

import shutil
from pathlib import Path


def reset_teach(*, device_id: str = "555c96f0") -> None:
    root = Path(__file__).resolve().parents[2] / "data" / "teach"
    if root.exists():
        shutil.rmtree(root)
        print(f"removed {root}")
    for sub in ("episodes", "shots", "skills", "replay"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    print(f"recreated empty {root}")

    try:
        from app.learning.store import LearningStore

        store = LearningStore()
        with store._conn() as conn:  # noqa: SLF001
            n = conn.execute(
                "DELETE FROM device_memory WHERE device_id=? AND ui_key=?",
                (device_id, "comments_icon"),
            ).rowcount
            n2 = conn.execute(
                "DELETE FROM grounding_examples WHERE device_id=? AND anchor=?",
                (device_id, "comments_icon"),
            ).rowcount
        print(f"cleared LearningStore comments_icon: memory={n} grounding={n2}")
    except Exception as exc:
        print(f"LearningStore cleanup skipped: {exc}")


if __name__ == "__main__":
    reset_teach()
