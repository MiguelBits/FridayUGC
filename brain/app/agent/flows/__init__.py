"""Deterministic Instagram navigation flows + surface evaluation."""

from .ads import is_sponsored_ad
from .defs import FLOW_OPEN_COMMENTS, FLOW_OPEN_REELS, FlowDef, FlowStep, comments_icon_xy
from .memory import record_anchor_outcome
from .surface import SurfaceLabel, classify_surface

__all__ = [
    "FLOW_OPEN_COMMENTS",
    "FLOW_OPEN_REELS",
    "FlowDef",
    "FlowStep",
    "SurfaceLabel",
    "classify_surface",
    "comments_icon_xy",
    "is_sponsored_ad",
    "record_anchor_outcome",
]
