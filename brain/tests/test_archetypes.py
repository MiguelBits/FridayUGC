"""Content archetype loader tests."""

from __future__ import annotations

from app.ugc.archetypes import archetype_prompt_block, load_archetypes, pick_archetype


def test_archetypes_load():
    items = load_archetypes()
    assert len(items) >= 5
    assert "hook" in items[0]


def test_pick_archetype_gym_hint():
    arch = pick_archetype(pillar_hint="leg day gym")
    assert arch is not None
    assert any("gym" in p.lower() for p in arch.get("pillars", []))


def test_archetype_prompt_block():
    arch = pick_archetype()
    block = archetype_prompt_block(arch)
    assert "hook archetype" in block
