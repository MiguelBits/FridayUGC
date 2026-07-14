from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Persona:
    key: str
    name: str
    handle: str
    system_prompt: str
    identity_anchor: str
    pillars: tuple[str, ...]
    best_lanes: tuple[str, ...]
    # Verdict / close rotation pool (never the same one twice in a batch).
    verdict_pool: tuple[str, ...] = field(default_factory=tuple)
    gym_close_pool: tuple[str, ...] = field(default_factory=tuple)


def _load(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


LORENA = Persona(
    key="lorena",
    name="Lorena Mor",
    handle="@itslorenamor",
    system_prompt=_load("lorena_system_prompt.md"),
    identity_anchor=(
        "Same woman from reference — pale green eyes, long black wavy hair, "
        "warm tan skin, natural makeup."
    ),
    pillars=("gym / leg day", "clean eating", "outfit try-on", "Miami lifestyle"),
    best_lanes=("A", "B", "D", "E"),
    verdict_pool=(
        "This combo is it.",
        "Ten out of ten.",
        "I'm dead.",
        "Keeping it.",
        "Still thinking about it honestly.",
        "No returns.",
    ),
    gym_close_pool=(
        "Quads paid for this.",
        "You skip legs — I don't.",
        "Burned today. Worth it.",
        "Glutes cooked. Comment if you quit.",
        "Prove you train legs below.",
    ),
)

_REGISTRY: dict[str, Persona] = {LORENA.key: LORENA}


@lru_cache
def get_persona(key: str = "lorena") -> Persona:
    p = _REGISTRY.get(key.lower())
    if p is None:
        raise ValueError(f"Unknown persona: {key!r}. Known: {list(_REGISTRY)}")
    return p
