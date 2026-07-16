"""Deterministic replay of taught skills (no vision / no Y-offset ladder)."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from brain.adb import adb as adb_mod
from brain.adb.device import device_id_from_serial, resolve_serial, session_prep
from brain.adb.executor import execute, settle_ms
from brain.adb.gestures import reels_next_swipe, tap_jittered
from brain.adb.screenshot import capture_png
from brain.adb.uiauto import dump_texts

from .classify import is_ad_reel, score_open_comments
from .reels import ensure_on_reels
from .store import TeachStore

logger = logging.getLogger(__name__)


def _save_png(path: Path, serial: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png(serial=serial))


def _escape_once(w: int, h: int, serial: Optional[str]) -> None:
    execute("press", {"key": "back"}, screen_width=w, screen_height=h, serial=serial, mode="full")
    time.sleep(0.7)


def run_replay(
    *,
    skill: str = "open_comments",
    trials: int = 10,
    serial: Optional[str] = None,
    open_reels: bool = True,
    store: TeachStore | None = None,
) -> dict[str, Any]:
    if skill != "open_comments":
        raise ValueError(f"replay only supports open_comments for now (got {skill})")

    store = store or TeachStore()
    serial = resolve_serial(serial)
    device_id = device_id_from_serial(serial)
    session_prep(serial=serial)

    skill_data = store.get_skill(skill, device_id)
    if not skill_data or int(skill_data.get("n_ok") or 0) < 1:
        raise RuntimeError(
            f"No taught skill for {skill} on device {device_id}. "
            "Run: python -m adb.teach record --skill open_comments"
        )

    x = int(skill_data["x"])
    y = int(skill_data["y"])
    w, h = adb_mod.wm_size(serial=serial)
    # Prefer fractions when screen size differs from teach-time.
    if skill_data.get("x_frac") and skill_data.get("y_frac"):
        x = max(1, min(w - 1, int(round(float(skill_data["x_frac"]) * w))))
        y = max(1, min(h - 1, int(round(float(skill_data["y_frac"]) * h))))

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = store.replay_dir / f"{skill}_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    before_dir = out_dir / "before"
    after_dir = out_dir / "after"
    before_dir.mkdir(exist_ok=True)
    after_dir.mkdir(exist_ok=True)

    print(f"Replay skill={skill} device={device_id} taught=({x},{y}) n_ok={skill_data.get('n_ok')}")
    print(f"Output: {out_dir}")

    if open_reels:
        print("Opening Reels (simple deeplink)…")
        _, w, h = ensure_on_reels(w=w, h=h, serial=serial, proof_dir=out_dir / "reels_entry")
        if skill_data.get("x_frac") and skill_data.get("y_frac"):
            x = max(1, min(w - 1, int(round(float(skill_data["x_frac"]) * w))))
            y = max(1, min(h - 1, int(round(float(skill_data["y_frac"]) * h))))

    results: list[dict[str, Any]] = []
    attempted = 0
    passed = 0
    skipped_ads = 0
    trial = 0
    max_attempts = trials * 3  # allow ad skips

    while attempted < trials and trial < max_attempts:
        trial += 1
        w, h = adb_mod.wm_size(serial=serial)
        before_texts = dump_texts(serial=serial)
        if is_ad_reel(before_texts):
            skipped_ads += 1
            print(f"  trial skip: ad reel — swipe")
            reels_next_swipe(w, h, serial=serial)
            time.sleep(0.9)
            continue

        tag = f"trial_{attempted:02d}"
        before_path = before_dir / f"{tag}.png"
        after_path = after_dir / f"{tag}.png"
        _save_png(before_path, serial)

        tap_jittered(x, y, serial=serial)
        time.sleep(settle_ms("tap") / 1000.0 + 0.4)

        _save_png(after_path, serial)
        after_texts = dump_texts(serial=serial)
        scored = score_open_comments(after_texts, before_texts=before_texts)
        ok = bool(scored["ok"])
        attempted += 1
        if ok:
            passed += 1

        row = {
            "trial": attempted - 1,
            "ok": ok,
            "surface": scored.get("surface"),
            "label_guess": scored.get("label_guess"),
            "tap_x": x,
            "tap_y": y,
            "before": str(before_path.relative_to(out_dir)).replace("\\", "/"),
            "after": str(after_path.relative_to(out_dir)).replace("\\", "/"),
            "after_texts_sample": after_texts[:12],
        }
        results.append(row)
        print(
            f"  [{attempted}/{trials}] {'PASS' if ok else 'FAIL'} "
            f"surface={scored.get('surface')} at ({x},{y})"
        )

        _escape_once(w, h, serial)
        if ok:
            # Next reel for variety on organic success.
            reels_next_swipe(w, h, serial=serial)
            time.sleep(0.8)
        else:
            # Fail may already have left a trap/share — one more back if needed.
            time.sleep(0.3)

    rate = (passed / attempted) if attempted else 0.0
    report = {
        "skill": skill,
        "device_id": device_id,
        "taught_x": x,
        "taught_y": y,
        "n_ok_teach": skill_data.get("n_ok"),
        "trials_requested": trials,
        "attempted": attempted,
        "passed": passed,
        "pass_rate": round(rate, 4),
        "skipped_ads": skipped_ads,
        "results": results,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nPass rate: {passed}/{attempted} = {rate:.0%}  (report: {report_path})")
    return report
