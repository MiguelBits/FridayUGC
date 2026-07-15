"""Content hook archetypes (instagram-ai-agent inspired patterns)."""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

_ARCHETYPES_PATH = Path(__file__).resolve().parents[2] / "data" / "content" / "archetypes.json"


def load_archetypes() -> list[dict[str, Any]]:
    if not _ARCHETYPES_PATH.is_file():
        return []
    return json.loads(_ARCHETYPES_PATH.read_text(encoding="utf-8"))


def pick_archetype(
    *,
    pillar_hint: str = "",
    lane_hint: str = "",
) -> dict[str, Any] | None:
    items = load_archetypes()
    if not items:
        return None
    hint = (pillar_hint or lane_hint).lower()
    if hint:
        parts = [w for w in hint.replace(",", " ").split() if w]
        matched = [
            a
            for a in items
            if any(
                any(part in p.lower() or p.lower() in hint for part in parts)
                for p in a.get("pillars", [])
            )
            or any(part in a.get("id", "").lower() for part in parts)
        ]
        if matched:
            return random.choice(matched)
    return random.choice(items)


def archetype_prompt_block(archetype: dict[str, Any] | None) -> str:
    if not archetype:
        return ""
    return (
        "\nUse this proven hook archetype (adapt, do not copy verbatim):\n"
        f"  id: {archetype.get('id')}\n"
        f"  hook: {archetype.get('hook')}\n"
        f"  formula: {archetype.get('formula')}\n"
        f"  pillars: {', '.join(archetype.get('pillars', []))}\n"
    )
