"""Capture device screenshot, resize, and base64-encode."""

from __future__ import annotations

import base64
import io
from typing import Optional

from PIL import Image

from . import adb

MAX_EDGE = 768
IG_PACKAGE = "com.instagram.android"


def capture_png(*, serial: Optional[str] = None) -> bytes:
    return adb.screencap_png(serial=serial)


def resize_png(raw: bytes, max_edge: int = MAX_EDGE) -> bytes:
    img = Image.open(io.BytesIO(raw))
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    scale = max_edge / longest
    new_size = (max(int(w * scale), 1), max(int(h * scale), 1))
    resized = img.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def to_base64(png_bytes: bytes) -> str:
    return base64.b64encode(png_bytes).decode("ascii")


def capture_b64(*, serial: Optional[str] = None, max_edge: int = MAX_EDGE) -> str:
    raw = capture_png(serial=serial)
    return to_base64(resize_png(raw, max_edge=max_edge))
