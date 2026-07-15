"""Verified screenshot+point exemplars for vision grounding (Layer B)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GroundingExample:
    anchor: str
    x: int
    y: int
    screen_width: int
    screen_height: int
    device_id: str = ""
    ig_version: str = ""


def format_exemplar_hints(examples: list[GroundingExample]) -> str:
    if not examples:
        return ""
    lines = ["VERIFIED_EXAMPLES (same anchor on this device — prefer similar placement):"]
    for ex in examples[:5]:
        lines.append(
            f"  - {ex.anchor}: tap center ({ex.x},{ex.y}) on {ex.screen_width}x{ex.screen_height}"
        )
    return "\n".join(lines) + "\n"
