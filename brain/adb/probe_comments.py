"""Probe: stay on Reels → skip ads → open comments N times with step screenshots.

Learns which Y offsets open the real comments sheet (not share, not ad landings).

Usage (Git Bash on Windows, from brain/):

  source .venv/Scripts/activate
  python -m adb.probe_comments --trials 20 --out data/probes/comments_open
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRAIN_ROOT = _REPO_ROOT / "brain"
for path in (_REPO_ROOT, _BRAIN_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from app.agent.flows.ads import is_home_feed_surface, is_sponsored_ad, is_trap_overlay, looks_like_comments_sheet  # noqa: E402
from app.agent.flows.defs import COMMENTS_ICON_Y_OFFSETS, comments_icon_xy, comments_y_frac_for_screen  # noqa: E402
from app.agent.flows.memory import record_anchor_outcome  # noqa: E402
from app.agent.flows.surface import SurfaceLabel, classify_surface, surface_signals  # noqa: E402
from brain.adb import adb as adb_mod  # noqa: E402
from brain.adb.device import device_id_from_serial, resolve_serial, session_prep  # noqa: E402
from brain.adb.executor import execute, settle_ms  # noqa: E402
from brain.adb.gestures import reels_next_swipe, tap_jittered  # noqa: E402
from brain.adb.nav import nav_reels_candidates, nav_xy  # noqa: E402
from brain.adb.observe import build_observe  # noqa: E402
from brain.adb.screenshot import capture_png  # noqa: E402
from brain.adb.uiauto import dump_texts  # noqa: E402

logger = logging.getLogger(__name__)


def _save_png(path: Path, serial: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png(serial=serial))


def _read_ui(serial: Optional[str]) -> list[str]:
    return dump_texts(serial=serial)


def _label(observe, texts: list[str]) -> tuple[SurfaceLabel, dict[str, Any]]:
    screen = observe.screen
    shot = (screen.screenshot_b64 or "").strip()
    label = classify_surface(
        screen, screenshot_b64=shot, activity=screen.activity or "", extra_texts=texts
    )
    signals = surface_signals(screen, screenshot_b64=shot, extra_texts=texts)
    return label, signals


def _escape_trap(w: int, h: int, serial: Optional[str]) -> None:
    """Leave cookie / lead-form / in-app browser."""
    # Prefer X in top-right of in-app browser, then back.
    tap_jittered(int(w * 0.93), int(h * 0.08), serial=serial)
    time.sleep(0.4)
    execute("press", {"key": "back"}, screen_width=w, screen_height=h, serial=serial)
    time.sleep(0.7)


def ensure_on_reels(
    *,
    w: int,
    h: int,
    serial: Optional[str],
    out_dir: Path,
) -> tuple[bool, int, int]:
    """Force Reels tab. Returns (ok, width, height)."""
    for attempt, (x, y, x_frac, y_frac) in enumerate(nav_reels_candidates(w, h)):
        logger.info(
            "Reels entry attempt %s x_frac=%.2f y_frac=%.3f → (%s,%s)",
            attempt + 1,
            x_frac,
            y_frac,
            x,
            y,
        )
        try:
            adb_mod.shell(
                "am start -a android.intent.action.VIEW -d instagram://reels com.instagram.android",
                serial=serial,
            )
        except adb_mod.AdbError:
            pass
        time.sleep(1.2)
        tap_jittered(x, y, serial=serial)
        time.sleep(settle_ms("navigate") / 1000.0)

        observe = build_observe(serial=serial, include_screenshot=True)
        w = observe.screen_width or w
        h = observe.screen_height or h
        texts = _read_ui(serial)
        label, _ = _label(observe, texts)
        _save_png(out_dir / f"00_reels_entry_try{attempt}.png", serial)

        on_home = label == SurfaceLabel.HOME_FEED or is_home_feed_surface(observe.screen, texts)
        if on_home:
            logger.warning("Still on home feed (Para ti) — retry nav")
            continue
        act = (observe.screen.activity or "").lower()
        strong_act = "clips" in act or ("reel" in act and "profile" not in act)
        if label in {SurfaceLabel.REELS_VIEWER, SurfaceLabel.AD_REEL} or strong_act:
            logger.info(
                "On Reels surface label=%s activity=%s texts_sample=%s",
                label.value,
                observe.screen.activity,
                texts[:8],
            )
            return True, w, h
        logger.warning(
            "Unclear after nav label=%s activity=%s — retry (do not trust UNKNOWN alone)",
            label.value,
            observe.screen.activity,
        )
    return False, w, h


def skip_ads_until_organic(
    *,
    w: int,
    h: int,
    serial: Optional[str],
    max_swipes: int = 8,
) -> tuple[bool, list[str]]:
    """Swipe past Patrocinado / sponsored until an organic reel (or give up)."""
    for i in range(max_swipes):
        observe = build_observe(serial=serial, include_screenshot=True)
        w = observe.screen_width or w
        h = observe.screen_height or h
        texts = _read_ui(serial)
        if is_trap_overlay(observe.screen, texts):
            logger.info("Trap overlay — escaping before ad check")
            _escape_trap(w, h, serial)
            continue
        if is_home_feed_surface(observe.screen, texts):
            logger.warning("Fell back to home — re-entering Reels")
            x, y = nav_xy("reels", w, h)
            tap_jittered(x, y, serial=serial)
            time.sleep(1.5)
            continue
        if is_sponsored_ad(observe.screen, texts):
            logger.info("Ad detected (Patrocinado/CTA) — swipe %s/%s", i + 1, max_swipes)
            reels_next_swipe(w, h, serial=serial)
            time.sleep(1.0)
            continue
        # Organic enough to try comments.
        return True, texts
    return False, _read_ui(serial)


def run_probe(
    *,
    trials: int,
    out_dir: Path,
    serial: Optional[str] = None,
) -> dict[str, Any]:
    serial = resolve_serial(serial)
    device_id = device_id_from_serial(serial)
    session_prep(serial=serial)
    out_dir.mkdir(parents=True, exist_ok=True)
    before_dir = out_dir / "before"
    after_dir = out_dir / "after"
    before_dir.mkdir(exist_ok=True)
    after_dir.mkdir(exist_ok=True)

    observe = build_observe(serial=serial, include_screenshot=True)
    w, h = observe.screen_width or 1080, observe.screen_height or 2400
    logger.info("Device %s size=%sx%s — ensuring Reels (not Home)", device_id[:12], w, h)

    open_reels_ok, w, h = ensure_on_reels(w=w, h=h, serial=serial, out_dir=out_dir)
    _save_png(out_dir / "00_reels_entry.png", serial)
    if not open_reels_ok:
        logger.error("Could not open Reels tab — aborting probe (fix nav first)")
        report = {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "device_id": device_id,
            "trials": 0,
            "open_reels_ok": False,
            "error": "failed_open_reels",
            "screen": {"width": w, "height": h},
        }
        (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    base_y = comments_y_frac_for_screen(w, h)
    details: list[dict[str, Any]] = []
    comments_ok = 0
    wrong = 0
    ads_skipped = 0
    traps = 0
    no_change = 0
    offset_wins: dict[str, int] = {}

    for i in range(trials):
        organic, _ = skip_ads_until_organic(w=w, h=h, serial=serial)
        if not organic:
            logger.warning("Trial %s: only ads — counting as skip", i + 1)
            ads_skipped += 1
            details.append({"trial": i, "outcome": "ads_only"})
            continue

        offset = COMMENTS_ICON_Y_OFFSETS[i % len(COMMENTS_ICON_Y_OFFSETS)]
        y_frac = base_y + offset
        x, y = comments_icon_xy(w, h, y_frac=y_frac)

        before = build_observe(serial=serial, include_screenshot=True)
        w = before.screen_width or w
        h = before.screen_height or h
        x, y = comments_icon_xy(w, h, y_frac=y_frac)
        before_texts = _read_ui(serial)
        before_path = before_dir / f"trial_{i:02d}_y{y_frac:.3f}.png"
        _save_png(before_path, serial)

        if is_sponsored_ad(before.screen, before_texts):
            logger.info("Trial %s before-tap still ad — swipe and retry later", i + 1)
            reels_next_swipe(w, h, serial=serial)
            ads_skipped += 1
            details.append({"trial": i, "outcome": "ad_before_tap", "y_frac": y_frac})
            time.sleep(0.8)
            continue

        logger.info("Trial %s/%s tap comments (%s,%s) y_frac=%.3f base=%.3f", i + 1, trials, x, y, y_frac, base_y)
        execute(
            "tap",
            {"x": x, "y": y, "ui_key": "comments_icon"},
            screen_width=w,
            screen_height=h,
            serial=serial,
            mode="full",
        )
        time.sleep(1.2)

        after = build_observe(serial=serial, include_screenshot=True)
        after_texts = _read_ui(serial)
        after_path = after_dir / f"trial_{i:02d}_y{y_frac:.3f}.png"
        _save_png(after_path, serial)
        label, signals = _label(after, after_texts)

        outcome = "unknown"
        if is_trap_overlay(after.screen, after_texts) or label == SurfaceLabel.TRAP:
            outcome = "trap_ad_or_browser"
            traps += 1
            record_anchor_outcome(device_id, "comments_icon", x=x, y=y, success=False, screen_width=w, screen_height=h)
            _escape_trap(w, h, serial)
        elif looks_like_comments_sheet(after.screen, after_texts) or label == SurfaceLabel.COMMENTS_SHEET:
            outcome = "comments_ok"
            comments_ok += 1
            key = f"{y_frac:.3f}"
            offset_wins[key] = offset_wins.get(key, 0) + 1
            record_anchor_outcome(
                device_id,
                "comments_icon",
                x=x,
                y=y,
                success=True,
                screen_width=w,
                screen_height=h,
                screenshot_b64=after.screen.screenshot_b64,
                ig_version=after.ig_version or "",
            )
            execute("press", {"key": "back"}, screen_width=w, screen_height=h, serial=serial)
            time.sleep(0.8)
        elif label == SurfaceLabel.SHARE_SHEET:
            outcome = "wrong_sheet_share"
            wrong += 1
            record_anchor_outcome(device_id, "comments_icon", x=x, y=y, success=False, screen_width=w, screen_height=h)
            execute("press", {"key": "back"}, screen_width=w, screen_height=h, serial=serial)
            time.sleep(0.8)
        else:
            outcome = "no_change_or_unknown"
            no_change += 1
            record_anchor_outcome(device_id, "comments_icon", x=x, y=y, success=False, screen_width=w, screen_height=h)

        details.append(
            {
                "trial": i,
                "x": x,
                "y": y,
                "y_frac": y_frac,
                "outcome": outcome,
                "label": label.value,
                "signals": signals,
                "before_texts": before_texts[:20],
                "after_texts": after_texts[:20],
                "before": str(before_path),
                "after": str(after_path),
                "activity": after.screen.activity,
            }
        )
        logger.info("Trial %s outcome=%s label=%s after_texts=%s", i + 1, outcome, label.value, after_texts[:6])

        # Next organic reel for the following trial.
        reels_next_swipe(w, h, serial=serial)
        time.sleep(0.9)

    best_y = None
    if offset_wins:
        best_y = max(offset_wins.items(), key=lambda kv: kv[1])[0]

    report = {
        "ran_at": datetime.now(timezone.utc).isoformat(),
        "device_id": device_id,
        "trials": trials,
        "open_reels_ok": True,
        "open_comments_ok": comments_ok,
        "wrong_sheet": wrong,
        "traps": traps,
        "ads_skipped": ads_skipped,
        "no_change": no_change,
        "best_y_frac": float(best_y) if best_y else None,
        "base_y_frac": base_y,
        "offset_wins": offset_wins,
        "screen": {"width": w, "height": h},
        "trials_detail": details,
        "docs": "docs/flows/OPEN_COMMENTS.md",
        "note": "Learning = score Y offsets that open Comentários sheet on organic reels; ads are swiped away.",
    }
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info(
        "Probe done: comments_ok=%s/%s traps=%s ads_skipped=%s best_y=%s → %s",
        comments_ok,
        trials,
        traps,
        ads_skipped,
        best_y,
        report_path,
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe open Reels → skip ads → open comments")
    parser.add_argument("--trials", type=int, default=20)
    parser.add_argument("--out", default="data/probes/comments_open")
    parser.add_argument("--serial", default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    out = Path(args.out)
    if not out.is_absolute():
        out = _BRAIN_ROOT / out
    run_probe(trials=args.trials, out_dir=out, serial=args.serial)


if __name__ == "__main__":
    main()
