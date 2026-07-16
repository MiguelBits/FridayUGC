"""Interactive teach session — human performs the comment-likes reel flow on the phone."""

from __future__ import annotations

import logging
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from brain.adb import adb as adb_mod
from brain.adb.device import device_id_from_serial, resolve_serial, session_prep
from brain.adb.gestures import reels_next_swipe
from brain.adb.screenshot import capture_png
from brain.adb.uiauto import dump_texts

from .coords import parse_coord_input, pick_point_on_image
from .reels import ensure_on_reels
from .store import (
    IMPLEMENTED_SKILLS,
    VALID_LABELS,
    VALID_SKILLS,
    TeachStore,
    suggest_label_from_texts,
)

logger = logging.getLogger(__name__)

# First teach flow: put likes on comments in a reel (docs/flows/COMMENT_LIKES_LOOP.md).
FULL_LOOP_LIKES_DEFAULT = 2

# Steps that teach a tap target (need coords on the BEFORE / inherited shot).
_TAP_SKILLS = frozenset({"open_comments", "like_comment"})

_CONFIRM_PROMPTS: dict[str, str] = {
    "open_comments": "Evidence OK — comments sheet open? [Y/n]",
    "like_comment": "Evidence OK — still on comments after the like? [Y/n]",
    "scroll_comments": "Evidence OK — comments list scrolled? [Y/n]",
    "close_comments": "Evidence OK — comments closed, back on Reels? [Y/n]",
    "next_reel": "Evidence OK — next reel showing? [Y/n]",
}

_ACTION_HINTS: dict[str, str] = {
    "open_comments": "OPEN COMMENTS (tap the comments icon)",
    "like_comment": "LIKE a comment (tap a comment-row heart, not the reel like)",
    "scroll_comments": "SCROLL the comments list (finger up inside the sheet)",
    "close_comments": "CLOSE comments (press Back / swipe sheet down)",
    "next_reel": "NEXT REEL (swipe up to the next reel)",
}


def _save_png(path: Path, serial: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png(serial=serial))


def _prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return "q"


def _ask_fail_reason(suggested: str | None) -> str:
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


def _ask_label(suggested: str | None, *, skill: str = "open_comments") -> str:
    hint = ""
    if suggested and suggested != "ok":
        hint = f" (auto-guess={suggested})"
    confirm = _CONFIRM_PROMPTS.get(skill, f"{skill} ok? [Y/n]")
    while True:
        raw = _prompt(f"{confirm}{hint}: ").lower()
        if raw in {"", "y", "yes"}:
            print("  → ok")
            return "ok"
        if raw in {"n", "no"}:
            label = _ask_fail_reason(suggested)
            print(f"  → {label}")
            return label
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
    print("  Coords: click the BEFORE image (where you tapped), or type x,y / x% y%.")
    clicked = pick_point_on_image(before_path, screen_width, screen_height)
    if clicked:
        x, y, xf, yf = clicked
        print(f"  Clicked → ({x}, {y})  frac=({xf:.3f}, {yf:.3f})")
        return x, y, xf, yf

    while True:
        raw = _prompt("  Type coords (or Enter to skip): ")
        if not raw:
            if required:
                print("  ok tap steps need coords — please provide them.")
                continue
            return None, None, None, None
        parsed = parse_coord_input(raw, screen_width=screen_width, screen_height=screen_height)
        if parsed:
            x, y, xf, yf = parsed
            print(f"  Parsed → ({x}, {y})  frac=({xf:.3f}, {yf:.3f})")
            return x, y, xf, yf
        print("  Could not parse. Examples: 1320,1680  |  0.92,0.52  |  92% 52%")


def _record_step(
    *,
    skill: str,
    store: TeachStore,
    device_id: str,
    serial: Optional[str],
    screen_w: int,
    screen_h: int,
    parent_id: str | None = None,
    step_index: int | None = None,
    inherit_after_path: Path | None = None,
    need_coords: bool | None = None,
) -> tuple[str, dict | None, Path | None]:
    """
    One step in the reel flow.

    - If inherit_after_path is set: that AFTER shot becomes this step's BEFORE
      (chained evidence — same picture the previous step proved).
    - Else: capture a fresh BEFORE from the phone.
    - Always capture a new AFTER after you act (proof of this step).

    Returns (status, episode, after_path) where status is ok|fail|ad|skip|quit.
    """
    if need_coords is None:
        need_coords = skill in _TAP_SKILLS

    episode_id = str(uuid.uuid4())
    before_rel = f"shots/{episode_id}_before.png"
    after_rel = f"shots/{episode_id}_after.png"
    before_path = store.root / before_rel
    after_path = store.root / after_rel
    before_path.parent.mkdir(parents=True, exist_ok=True)

    hint = _ACTION_HINTS.get(skill, skill)
    print(f"\n  ┌─ STEP {step_index}: {skill}")
    print(f"  │  Do on phone: {hint}")

    if inherit_after_path is not None and inherit_after_path.is_file():
        shutil.copy2(inherit_after_path, before_path)
        print(f"  │  BEFORE = previous AFTER (chained) → {before_rel}")
        before_texts = dump_texts(serial=serial)
    else:
        print("  │  Capturing fresh BEFORE…")
        _save_png(before_path, serial)
        before_texts = dump_texts(serial=serial)
        print(f"  │  BEFORE → {before_rel}")

    w, h = adb_mod.wm_size(serial=serial)
    if w > 0 and h > 0:
        screen_w, screen_h = w, h

    cmd = _prompt(
        "  │  When done on phone → Enter  (s=skip step, a=ad+next reel, q=quit): "
    ).lower()
    if cmd == "q":
        return "quit", None, inherit_after_path
    if cmd == "s":
        print("  └─ skipped")
        return "skip", None, inherit_after_path
    if cmd == "a":
        ep = {
            "episode_id": episode_id,
            "skill": skill,
            "label": "ad",
            "device_id": device_id,
            "screen_width": screen_w,
            "screen_height": screen_h,
            "tap_x": None,
            "tap_y": None,
            "tap_x_frac": None,
            "tap_y_frac": None,
            "before_path": before_rel.replace("\\", "/"),
            "after_path": before_rel.replace("\\", "/"),
            "before_texts": before_texts,
            "after_texts": before_texts,
            "parent_id": parent_id,
            "step_index": step_index,
            "chained_from": str(inherit_after_path.name) if inherit_after_path else None,
        }
        store.save_episode(ep, aggregate=False)
        print("  └─ labeled ad")
        return "ad", ep, before_path

    print("  │  Capturing AFTER (evidence)…")
    time.sleep(0.35)
    _save_png(after_path, serial)
    after_texts = dump_texts(serial=serial)
    print(f"  │  AFTER  → {after_rel}")

    suggested = suggest_label_from_texts(after_texts, before_texts, skill=skill)
    label = _ask_label(suggested, skill=skill)

    tap_x = tap_y = None
    tap_x_frac = tap_y_frac = None
    if need_coords and label == "ok":
        tap_x, tap_y, tap_x_frac, tap_y_frac = _ask_coords(
            before_path, screen_width=screen_w, screen_height=screen_h, required=True
        )
    elif need_coords and label != "ok":
        want = _prompt("  Record tap coords for this fail? [y/N]: ").lower()
        if want in {"y", "yes"}:
            tap_x, tap_y, tap_x_frac, tap_y_frac = _ask_coords(
                before_path, screen_width=screen_w, screen_height=screen_h, required=False
            )

    ep = {
        "episode_id": episode_id,
        "skill": skill,
        "label": label,
        "device_id": device_id,
        "screen_width": screen_w,
        "screen_height": screen_h,
        "tap_x": tap_x,
        "tap_y": tap_y,
        "tap_x_frac": tap_x_frac,
        "tap_y_frac": tap_y_frac,
        "before_path": before_rel.replace("\\", "/"),
        "after_path": after_rel.replace("\\", "/"),
        "before_texts": before_texts,
        "after_texts": after_texts,
        "parent_id": parent_id,
        "step_index": step_index,
        "chained_from": str(inherit_after_path.name) if inherit_after_path else None,
    }
    aggregate = bool(need_coords and label == "ok" and tap_x and tap_y)
    store.save_episode(ep, aggregate=aggregate)

    if need_coords:
        skill_data = store.get_skill(skill, device_id)
        if skill_data:
            print(
                f"  └─ saved {label}. skill n_ok={skill_data.get('n_ok')} "
                f"coord=({skill_data.get('x')}, {skill_data.get('y')})"
            )
        else:
            print(f"  └─ saved {label}")
    else:
        print(f"  └─ saved evidence {label} (no coord aggregate)")

    status = "ok" if label == "ok" else ("ad" if label == "ad" else "fail")
    return status, ep, after_path


def _swipe_next_reel(w: int, h: int, serial: Optional[str]) -> None:
    reels_next_swipe(w, h, serial=serial)
    time.sleep(0.9)


def run_record(
    *,
    skill: str,
    count: int = 10,
    likes_per_reel: int = FULL_LOOP_LIKES_DEFAULT,
    open_reels: bool = True,
    serial: Optional[str] = None,
    store: TeachStore | None = None,
) -> int:
    """Run interactive record loop. Returns number of reel-episodes completed."""
    if skill not in VALID_SKILLS:
        print(f"Unknown skill '{skill}'. Choose: {', '.join(sorted(VALID_SKILLS))}")
        return 0
    if skill not in IMPLEMENTED_SKILLS:
        print(
            f"Skill '{skill}' is not implemented yet. "
            f"Use: {', '.join(sorted(IMPLEMENTED_SKILLS))}"
        )
        return 0

    store = store or TeachStore()
    serial = resolve_serial(serial)
    device_id = device_id_from_serial(serial)
    session_prep(serial=serial)

    w, h = adb_mod.wm_size(serial=serial)
    print(f"Teach record skill={skill} device={device_id} screen={w}x{h}")
    if skill == "full_loop":
        print()
        print("FIRST FLOW — put likes on a reel (chained screenshots):")
        print("  1. open comments     → AFTER = proof we are in comments")
        print("  2. like a comment    → BEFORE = that proof; AFTER = after like")
        print("  3. scroll comments   → BEFORE = previous AFTER")
        print("  4. like another      → BEFORE = previous AFTER")
        print("  5. close comments    → BEFORE = previous AFTER")
        print("  6. next reel         → BEFORE = previous AFTER")
        print(f"Likes per reel: {likes_per_reel} (with scroll between likes).")
        print("You do every action on the phone; we screenshot + ask at each step.")
    elif skill == "like_comment":
        print("Assumes comments sheet is already open. Per step: like one comment heart.")
    else:
        print()
        print("*** open_comments ONLY — will NOT label like / scroll / close / next. ***")
        print("*** For the full reel flow use:  --skill full_loop --likes 2          ***")
        print("After each open, you can still press Y to continue into the full flow.")
    print("Commands anytime: s=skip  a=ad  q=quit")

    if open_reels:
        print("\nOpening Reels (deeplink + one Reels-tab tap)…")
        ok, w, h = ensure_on_reels(
            w=w,
            h=h,
            serial=serial,
            proof_dir=store.root / "shots" / "_reels_entry",
        )
        if not ok:
            print("Reels entry failed — open Reels yourself, then continue.")

    saved = 0
    while saved < count:
        parent_id = str(uuid.uuid4())
        print(f"\n{'=' * 60}")
        print(f"REEL EPISODE {saved + 1}/{count}  id={parent_id[:8]}")
        print(f"{'=' * 60}")

        if skill == "full_loop":
            status = _run_full_loop_episode(
                store=store,
                device_id=device_id,
                serial=serial,
                w=w,
                h=h,
                parent_id=parent_id,
                likes_per_reel=likes_per_reel,
            )
        elif skill == "like_comment":
            status, _, _ = _record_step(
                skill="like_comment",
                store=store,
                device_id=device_id,
                serial=serial,
                screen_w=w,
                screen_h=h,
                parent_id=parent_id,
                step_index=0,
            )
            if status == "ad":
                w, h = adb_mod.wm_size(serial=serial)
                _swipe_next_reel(w, h, serial)
        else:
            # open_comments-only — but offer to continue into full flow (common mistake).
            status, _ep, chain = _record_step(
                skill="open_comments",
                store=store,
                device_id=device_id,
                serial=serial,
                screen_w=w,
                screen_h=h,
                parent_id=parent_id,
                step_index=0,
            )
            if status == "ad":
                w, h = adb_mod.wm_size(serial=serial)
                _swipe_next_reel(w, h, serial)
            elif status == "ok" and chain is not None:
                cont = _prompt(
                    "Continue full flow from here "
                    "(like → scroll → like → close → next)? [Y/n]: "
                ).lower()
                if cont in {"", "y", "yes"}:
                    status = _run_after_comments_open(
                        store=store,
                        device_id=device_id,
                        serial=serial,
                        w=w,
                        h=h,
                        parent_id=parent_id,
                        likes_per_reel=likes_per_reel,
                        chain=chain,
                        step=1,
                    )
                else:
                    # Leave sheet / advance so next BEFORE is a clean reel.
                    w, h = adb_mod.wm_size(serial=serial)
                    print("  Close comments + swipe next yourself, or wait — advancing reel…")
                    _swipe_next_reel(w, h, serial)

        if status == "quit":
            print("Quit.")
            break
        if status == "skip":
            print("Skipped episode.")
            continue

        saved += 1

    print(f"\nDone. Completed {saved} reel episode(s) under {store.root}")
    return saved


def _run_after_comments_open(
    *,
    store: TeachStore,
    device_id: str,
    serial: Optional[str],
    w: int,
    h: int,
    parent_id: str,
    likes_per_reel: int,
    chain: Path | None,
    step: int,
) -> str:
    """Continue reel after comments are open: like → scroll → like → close → next."""
    likes_target = max(1, likes_per_reel)
    likes_ok = 0

    for i in range(likes_target):
        status, _ep, chain = _record_step(
            skill="like_comment",
            store=store,
            device_id=device_id,
            serial=serial,
            screen_w=w,
            screen_h=h,
            parent_id=parent_id,
            step_index=step,
            inherit_after_path=chain,
        )
        step += 1
        if status == "quit":
            return "quit"
        if status == "ad":
            w, h = adb_mod.wm_size(serial=serial)
            _swipe_next_reel(w, h, serial)
            return "ad"
        if status == "ok":
            likes_ok += 1
        elif status == "fail":
            print("  Like failed — continue to close/next so the reel can finish.")
            break

        if i < likes_target - 1 and status == "ok":
            status, _ep, chain = _record_step(
                skill="scroll_comments",
                store=store,
                device_id=device_id,
                serial=serial,
                screen_w=w,
                screen_h=h,
                parent_id=parent_id,
                step_index=step,
                inherit_after_path=chain,
                need_coords=False,
            )
            step += 1
            if status == "quit":
                return "quit"
            if status == "ad":
                w, h = adb_mod.wm_size(serial=serial)
                _swipe_next_reel(w, h, serial)
                return "ad"

    status, _ep, chain = _record_step(
        skill="close_comments",
        store=store,
        device_id=device_id,
        serial=serial,
        screen_w=w,
        screen_h=h,
        parent_id=parent_id,
        step_index=step,
        inherit_after_path=chain,
        need_coords=False,
    )
    step += 1
    if status == "quit":
        return "quit"
    if status == "ad":
        w, h = adb_mod.wm_size(serial=serial)
        _swipe_next_reel(w, h, serial)
        return "ad"

    status, _ep, _chain = _record_step(
        skill="next_reel",
        store=store,
        device_id=device_id,
        serial=serial,
        screen_w=w,
        screen_h=h,
        parent_id=parent_id,
        step_index=step,
        inherit_after_path=chain,
        need_coords=False,
    )
    if status == "quit":
        return "quit"

    print(f"\n  Reel episode done. likes_ok={likes_ok}/{likes_target}")
    return "ok" if likes_ok > 0 else "fail"


def _run_full_loop_episode(
    *,
    store: TeachStore,
    device_id: str,
    serial: Optional[str],
    w: int,
    h: int,
    parent_id: str,
    likes_per_reel: int,
) -> str:
    """One reel: open_comments → like → (scroll → like)* → close → next_reel."""
    step = 0

    status, _ep, chain = _record_step(
        skill="open_comments",
        store=store,
        device_id=device_id,
        serial=serial,
        screen_w=w,
        screen_h=h,
        parent_id=parent_id,
        step_index=step,
        inherit_after_path=None,
    )
    step += 1
    if status in {"quit", "skip", "ad"}:
        if status == "ad":
            w, h = adb_mod.wm_size(serial=serial)
            _swipe_next_reel(w, h, serial)
        return status
    if status != "ok":
        print("  Comments not open — abort this reel, swipe next.")
        w, h = adb_mod.wm_size(serial=serial)
        _swipe_next_reel(w, h, serial)
        return status

    return _run_after_comments_open(
        store=store,
        device_id=device_id,
        serial=serial,
        w=w,
        h=h,
        parent_id=parent_id,
        likes_per_reel=likes_per_reel,
        chain=chain,
        step=step,
    )
