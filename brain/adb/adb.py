"""Low-level ADB subprocess wrapper with retry."""

from __future__ import annotations

import subprocess
import time
from typing import Optional

DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 30.0


class AdbError(Exception):
    """ADB command failed after retries."""


def _base_cmd(serial: Optional[str]) -> list[str]:
    cmd = ["adb"]
    if serial:
        cmd.extend(["-s", serial])
    return cmd


def run_adb(
    args: list[str],
    *,
    serial: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
) -> bytes:
    cmd = _base_cmd(serial) + args
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)
            if result.returncode != 0:
                err_text = result.stderr.decode("utf-8", errors="replace").strip()
                raise AdbError(err_text or f"adb exited {result.returncode}")
            return result.stdout
        except (subprocess.TimeoutExpired, AdbError, OSError) as exc:
            last_err = exc
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))
    raise AdbError(str(last_err))


def shell(command: str, *, serial: Optional[str] = None) -> str:
    return run_adb(["shell", command], serial=serial).decode("utf-8", errors="replace")


def tap(x: int, y: int, *, serial: Optional[str] = None) -> None:
    shell(f"input tap {x} {y}", serial=serial)


def swipe(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
    *,
    serial: Optional[str] = None,
) -> None:
    shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}", serial=serial)


def keyevent(code: int | str, *, serial: Optional[str] = None) -> None:
    shell(f"input keyevent {code}", serial=serial)


def screencap_png(*, serial: Optional[str] = None) -> bytes:
    return run_adb(["exec-out", "screencap", "-p"], serial=serial, timeout=15.0)


def wm_size(*, serial: Optional[str] = None) -> tuple[int, int]:
    out = shell("wm size", serial=serial)
    for line in out.splitlines():
        if "x" not in line:
            continue
        if "size" in line.lower() or "Override" in line or "Physical" in line:
            part = line.split(":")[-1].strip()
            if "x" in part:
                w_str, h_str = part.lower().split("x", 1)
                try:
                    return int(w_str.strip()), int(h_str.strip())
                except ValueError:
                    continue
    return 1080, 2400


def list_devices() -> list[str]:
    out = subprocess.run(
        ["adb", "devices"],
        capture_output=True,
        text=True,
        timeout=10.0,
        check=False,
    )
    devices: list[str] = []
    for line in out.stdout.splitlines()[1:]:
        line = line.strip()
        if not line or "\t" not in line:
            continue
        serial, state = line.split("\t", 1)
        if state.strip() == "device":
            devices.append(serial.strip())
    return devices
