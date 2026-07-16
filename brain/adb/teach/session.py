"""Interactive teach session — human performs actions on the phone."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Optional

from brain.adb import adb as adb_mod
from brain.adb.device import device_id_from_serial, resolve_serial, session_prep
from brain.adb.executor import execute, settle_ms
from brain.adb.gestures import reels_next_swipe
from brain.adb.screenshot import capture_png
from brain.adb.uiauto import dump_texts

from .coords import parse_coord_input, pick_point_on_image
from .store import IMPLEMENTED_SKILLS, VALID_LABELS, VALID_SKILLS, TeachStore, suggest_label_from_texts

logger = logging.getLogger(__name__)


def _save_png(path: Path, serial: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png(serial=serial))


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return "q"


def _ask_fail_reason(suggested: str | None) -> str:
    """Pick a non-ok label. Enter accepts suggested fail-type (default fail)."""
    default = suggested if suggested and suggested != "ok" else "fail"
    fail_choices = sorted(VALID_LABELS - {"ok"})
    while True:
        raw = _prompt(
            f"What went wrong? [{default}] ({'/'.join(fail_choices)}): "
        ).lower()
        if raw == "":
            return default
        if raw in VALID_LABELS and raw != "ok":
            return raw
        if raw == "ok":
            return "ok"
        print(f"  Need one of: {', '.join(fail_choices)} (or Enter for {default})")


def _ask_label(suggested: str | None) -> str:
    """Final confirm: Enter/Y = ok (correct). N = pick fail reason."""
    hint = ""
    if suggested and suggested != "ok":
        hint = f" (auto-guess={suggested})"
    while True:
        raw = _prompt(f"Comments opened correctly? [Y/n]{hint}: ").lower()
        if raw in {"", "y", "yes"}:
            print("  → ok")
            return "ok"
        if raw in {"n", "no"}:
            label = _ask_fail_reason(suggested)
            print(f"  → {label}")
            return label
        # Allow typing a label directly (power users).
        if raw in VALID_LABELS:
            print(f"  → {raw}")
            return raw
        print("  Y or Enter = correct (ok). N = not correct, then pick reason.")


def _ask_coords(
    before_path: Path,
    *,
    screen_width: int,
    screen_height: int,
    required: bool,
) -> tuple[int | None, int | None, float | None, float | None]:
    print("Coords: click the BEFORE image, or type x,y / x% y% (Enter to skip).")
    clicked = pick_point_on_image(before_path, screen_width, screen_height)
    if clicked:
        x, y, xf, yf = clicked
        print(f"  Clicked → ({x}, {y})  frac=({xf:.3f}, {yf:.3f})")
        return x, y, xf, yf

    while True:
        raw = _prompt("  Type coords (or Enter to skip): ")
        if not raw:
            if required:
                print("  ok labels need coords — please provide them.")
                continue
            return None, None, None, None
        parsed = parse_coord_input(raw, screen_width=screen_width, screen_height=screen_height)
        if parsed:
            x, y, xf, yf = parsed
            print(f"  Parsed → ({x}, {y})  frac=({xf:.3f}, {yf:.3f})")
            return x, y, xf, yf
        print("  Could not parse. Examples: 1320,1680  |  0.92,0.52  |  92% 52%")


def run_record(
    *,
    skill: str,
    count: int = 10,
    open_reels: bool = False,
    serial: Optional[str] = None,
    store: TeachStore | None = None,
) -> int:
    """Run interactive record loop. Returns number of episodes saved."""
    if skill not in VALID_SKILLS:
        print(f"Unknown skill '{skill}'. Choose: {', '.join(sorted(VALID_SKILLS))}")
        return 0
    if skill not in IMPLEMENTED_SKILLS:
        print(f"Skill '{skill}' is not implemented yet (phase 2). Use open_comments.")
        return 0

    store = store or TeachStore()
    serial = resolve_serial(serial)
    device_id = device_id_from_serial(serial)
    session_prep(serial=serial)

    w, h = adb_mod.wm_size(serial=serial)
    print(f"Teach record skill={skill} device={device_id} screen={w}x{h}")
    print("Per episode: do the action on the phone, then Enter. Commands: s=skip a=ad q=quit")

    if open_reels:
        print("Opening Reels (deterministic deeplink + tab)…")
        execute("open_reels", {}, screen_width=w, screen_height=h, serial=serial, mode="full")
        time.sleep(settle_ms("open_reels") / 1000.0)
        w, h = adb_mod.wm_size(serial=serial)

    saved = 0
    while saved < count:
        episode_id = str(uuid.uuid4())
        before_rel = f"shots/{episode_id}_before.png"
        after_rel = f"shots/{episode_id}_after.png"
        before_path = store.root / before_rel
        after_path = store.root / after_rel

        print(f"\n--- Episode {saved + 1}/{count} ({episode_id[:8]}) ---")
        print("Capturing BEFORE…")
        _save_png(before_path, serial)
        before_texts = dump_texts(serial=serial)
        w, h = adb_mod.wm_size(serial=serial)

        cmd = _prompt(
            "Perform open_comments on the phone, then Enter "
            "(s=skip, a=mark ad+swipe, q=quit): "
        ).lower()
        if cmd == "q":
            print("Quit.")
            break
        if cmd == "s":
            print("Skipped.")
            continue
        if cmd == "a":
            ep = {
                "episode_id": episode_id,
                "skill": skill,
                "label": "ad",
                "device_id": device_id,
                "screen_width": w,
                "screen_height": h,
                "tap_x": None,
                "tap_y": None,
                "tap_x_frac": None,
                "tap_y_frac": None,
                "before_path": before_rel.replace("\\", "/"),
                "after_path": before_rel.replace("\\", "/"),
                "before_texts": before_texts,
                "after_texts": before_texts,
            }
            store.save_episode(ep, aggregate=False)
            print("Labeled ad (not stored as success). Swiping to next reel…")
            reels_next_swipe(w, h, serial=serial)
            time.sleep(0.9)
            continue

        print("Capturing AFTER…")
        time.sleep(0.35)
        _save_png(after_path, serial)
        after_texts = dump_texts(serial=serial)

        suggested = suggest_label_from_texts(after_texts, before_texts)
        label = _ask_label(suggested)

        tap_x = tap_y = None
        tap_x_frac = tap_y_frac = None
        if label == "ok":
            tap_x, tap_y, tap_x_frac, tap_y_frac = _ask_coords(
                before_path, screen_width=w, screen_height=h, required=True
            )
        else:
            want = _prompt("Record tap coords for this fail? [y/N]: ").lower()
            if want in {"y", "yes"}:
                tap_x, tap_y, tap_x_frac, tap_y_frac = _ask_coords(
                    before_path, screen_width=w, screen_height=h, required=False
                )

        ep = {
            "episode_id": episode_id,
            "skill": skill,
            "label": label,
            "device_id": device_id,
            "screen_width": w,
            "screen_height": h,
            "tap_x": tap_x,
            "tap_y": tap_y,
            "tap_x_frac": tap_x_frac,
            "tap_y_frac": tap_y_frac,
            "before_path": before_rel.replace("\\", "/"),
            "after_path": after_rel.replace("\\", "/"),
            "before_texts": before_texts,
            "after_texts": after_texts,
        }
        # Only ok with coords aggregates into skill / LearningStore.
        store.save_episode(ep, aggregate=(label == "ok" and bool(tap_x) and bool(tap_y)))
        saved += 1
        skill_data = store.get_skill(skill, device_id)
        if skill_data:
            print(
                f"Saved label={label}. Skill n_ok={skill_data.get('n_ok')} "
                f"coord=({skill_data.get('x')}, {skill_data.get('y')})"
            )
        else:
            print(f"Saved label={label} (no skill aggregate yet).")

        # Leave comments sheet / wrong sheet so next demo starts clean.
        if label in {"ok", "wrong_sheet", "trap"}:
            execute("press", {"key": "back"}, screen_width=w, screen_height=h, serial=serial, mode="full")
            time.sleep(0.6)

    print(f"\nDone. Saved {saved} episode(s) under {store.root}")
    return saved
