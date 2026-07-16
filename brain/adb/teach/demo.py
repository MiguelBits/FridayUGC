"""Show taught open_comments skill and try it once on the phone."""

from __future__ import annotations

import json
import time
from pathlib import Path

from brain.adb import adb as adb_mod
from brain.adb.device import device_id_from_serial, resolve_serial, session_prep
from brain.adb.executor import execute, settle_ms
from brain.adb.gestures import tap_jittered
from brain.adb.screenshot import capture_png
from brain.adb.uiauto import dump_texts

from .classify import score_open_comments
from .reels import ensure_on_reels
from .store import TeachStore


def run_demo(*, trials: int = 3, serial: str | None = None, store: TeachStore | None = None) -> dict:
    store = store or TeachStore()
    serial = resolve_serial(serial)
    device_id = device_id_from_serial(serial)

    # Rebuild skill from current ok episodes (drops deleted bad demos).
    skill = store.aggregate_skill("open_comments", device_id)
    if not skill:
        raise RuntimeError(f"No ok demos for open_comments on {device_id}")

    print("=== What we learnt ===")
    print(json.dumps(skill, indent=2, ensure_ascii=False))
    print()

    ok_eps = store.list_episodes(skill="open_comments", device_id=device_id, label="ok")
    print(f"ok demos: {len(ok_eps)}")
    for ep in ok_eps:
        print(
            f"  {ep['episode_id'][:8]}  tap=({ep.get('tap_x')}, {ep.get('tap_y')}) "
            f"frac=({ep.get('tap_x_frac'):.3f}, {ep.get('tap_y_frac'):.3f})"
        )
    print()

    session_prep(serial=serial)
    w, h = adb_mod.wm_size(serial=serial)
    x = max(1, min(w - 1, int(round(float(skill["x_frac"]) * w))))
    y = max(1, min(h - 1, int(round(float(skill["y_frac"]) * h))))

    out = store.replay_dir / "demo_latest"
    out.mkdir(parents=True, exist_ok=True)
    print("Opening Reels (simple deeplink)…")
    _, w, h = ensure_on_reels(w=w, h=h, serial=serial, proof_dir=out / "reels_entry")
    x = max(1, min(w - 1, int(round(float(skill["x_frac"]) * w))))
    y = max(1, min(h - 1, int(round(float(skill["y_frac"]) * h))))
    print(f"=== Using taught tap ({x}, {y}) on {w}x{h} — {trials} trial(s) ===")
    results = []
    passed = 0
    for i in range(trials):
        w, h = adb_mod.wm_size(serial=serial)
        x = max(1, min(w - 1, int(round(float(skill["x_frac"]) * w))))
        y = max(1, min(h - 1, int(round(float(skill["y_frac"]) * h))))
        before = out / f"trial_{i:02d}_before.png"
        after = out / f"trial_{i:02d}_after.png"
        before.write_bytes(capture_png(serial=serial))
        before_texts = dump_texts(serial=serial)

        tap_jittered(x, y, serial=serial)
        time.sleep(settle_ms("tap") / 1000.0 + 0.5)

        after.write_bytes(capture_png(serial=serial))
        after_texts = dump_texts(serial=serial)
        scored = score_open_comments(after_texts, before_texts=before_texts)
        ok = bool(scored["ok"])
        if ok:
            passed += 1
        print(f"  trial {i + 1}: {'PASS' if ok else 'FAIL'} surface={scored.get('surface')}")
        results.append({"trial": i, "ok": ok, **scored, "tap": [x, y]})

        execute("press", {"key": "back"}, screen_width=w, screen_height=h, serial=serial, mode="full")
        time.sleep(0.7)

    report = {
        "skill": skill,
        "passed": passed,
        "trials": trials,
        "pass_rate": round(passed / trials, 4) if trials else 0.0,
        "results": results,
        "shots": str(out),
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nPass rate: {passed}/{trials}  shots: {out}")
    return report
