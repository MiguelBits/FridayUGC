"""Lightweight uiautomator dump — text signals when vision tree is empty."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Optional

from . import adb

_TEXT_ATTR = re.compile(r'text="([^"]*)"')
_DESC_ATTR = re.compile(r'content-desc="([^"]*)"')


def dump_texts(*, serial: Optional[str] = None, limit: int = 80) -> list[str]:
    """Return visible UI texts/content-descs from uiautomator dump."""
    try:
        adb.shell("uiautomator dump /sdcard/friday_ui.xml", serial=serial)
        raw = adb.shell("cat /sdcard/friday_ui.xml", serial=serial)
    except adb.AdbError:
        return []
    if not raw or "<hierarchy" not in raw:
        # Fallback: regex on partial dump
        texts: list[str] = []
        for m in _TEXT_ATTR.finditer(raw or ""):
            t = m.group(1).strip()
            if t:
                texts.append(t)
        for m in _DESC_ATTR.finditer(raw or ""):
            t = m.group(1).strip()
            if t:
                texts.append(t)
        return texts[:limit]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        texts = []
        for m in _TEXT_ATTR.finditer(raw):
            t = m.group(1).strip()
            if t:
                texts.append(t)
        return texts[:limit]
    out: list[str] = []
    for node in root.iter("node"):
        for key in ("text", "content-desc"):
            val = (node.attrib.get(key) or "").strip()
            if val and val not in out:
                out.append(val)
            if len(out) >= limit:
                return out
    return out
