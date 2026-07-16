"""Open Instagram Reels the way that already worked: deeplink + one Reels-tab tap.

Deeplink alone is unreliable on this phone (lands home / nowhere). The known-good
path from executor/nav is: VIEW intent, then tap center Reels at tall-phone Y.
No Y-offset ladder — one deterministic tab tap.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from brain.adb import adb as adb_mod
from brain.adb.executor import settle_ms
from brain.adb.gestures import tap_jittered
from brain.adb.nav import nav_xy
from brain.adb.screenshot import IG_PACKAGE, capture_png

REELS_URIS = (
    "instagram://reels",
    "https://www.instagram.com/reels/",
)


def _save_png(path: Path, serial: Optional[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png(serial=serial))


def ensure_on_reels(
    *,
    w: int,
    h: int,
    serial: Optional[str],
    proof_dir: Path | None = None,
) -> tuple[bool, int, int]:
    """Deeplink + single bottom-nav Reels tap (same as working open_reels)."""
    try:
        adb_mod.keyevent("KEYCODE_WAKEUP", serial=serial)
    except adb_mod.AdbError:
        pass

    # 1) Deeplink (best-effort — often insufficient alone)
    for uri in REELS_URIS:
        print(f"  Deeplink → {uri}")
        try:
            out = adb_mod.shell(
                f"am start -a android.intent.action.VIEW -d '{uri}' -p {IG_PACKAGE}",
                serial=serial,
            ).strip()
            if out:
                print(f"  am start: {out.splitlines()[0]}")
        except adb_mod.AdbError as exc:
            print(f"  Deeplink skip: {exc}")
        time.sleep(1.0)

    try:
        w, h = adb_mod.wm_size(serial=serial)
    except adb_mod.AdbError:
        pass

    # 2) Tap Reels tab once — on this IG build Reels is 2nd icon (~0.30), NOT center
    #    (center is Messages; that was the bug).
    x, y = nav_xy("reels", w, h)
    print(f"  Tab tap Reels once → ({x},{y})  [2nd tab x≈0.30, tall-phone Y]")
    tap_jittered(x, y, serial=serial)
    time.sleep(settle_ms("navigate") / 1000.0)

    if proof_dir is not None:
        _save_png(proof_dir / "reels_entry.png", serial)

    print("  Reels entry done. Your job: open comments when prompted.")
    return True, w, h
