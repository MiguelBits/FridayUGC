"""Bottom-nav coords for tall ADB phones (e.g. 1440x3216)."""

from __future__ import annotations

from adb.nav import (
    IG_NAV_X,
    is_tall_phone,
    nav_reels_candidates,
    nav_xy,
    nav_y_frac,
)


def test_tall_phone_aspect():
    assert is_tall_phone(1440, 3216)
    assert is_tall_phone(1080, 2400)  # 2.22 aspect — also tall
    assert not is_tall_phone(1080, 1920)


def test_reels_is_second_tab_not_messages():
    """Home | Reels | Messages | Search | Profile — Reels @ 0.30, Messages @ 0.50."""
    assert IG_NAV_X["reels"] == 0.30
    assert IG_NAV_X["inbox"] == 0.50
    assert IG_NAV_X["search"] == 0.70


def test_nav_xy_tall_phone_hits_reels_not_messages():
    x, y = nav_xy("reels", 1440, 3216)
    assert x == int(1440 * 0.30)
    assert y == int(3216 * 0.955)
    assert nav_y_frac(1440, 3216) == 0.955
    # Center would be Messages on this layout
    assert x != int(1440 * 0.50)


def test_nav_xy_shorter_phone():
    x, y = nav_xy("reels", 1080, 1920)
    assert x == int(1080 * 0.30)
    assert y == int(1920 * 0.965)


def test_reels_candidates_second_tab_first():
    cands = nav_reels_candidates(1440, 3216)
    assert cands[0][2] == 0.30  # x_frac — Reels second
    assert cands[0][3] == 0.955  # y_frac
    assert any(c[2] == 0.50 for c in cands)  # alternate center-Reels layout
