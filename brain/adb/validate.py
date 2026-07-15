"""Coordinate sanity checks before motor execution."""

from __future__ import annotations

from .safety_zones import block_reason


def validate_tap(x: int, y: int, screen_width: int, screen_height: int) -> str | None:
    return block_reason(x, y, screen_width, screen_height)
