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


def test_reels_is_center_tab():
    assert IG_NAV_X["reels"] == 0.50
    assert IG_NAV_X["search"] == 0.30


def test_nav_xy_tall_phone_hits_center_reels():
    x, y = nav_xy("reels", 1440, 3216)
    assert x == int(1440 * 0.50)
    assert y == int(3216 * 0.955)
    assert nav_y_frac(1440, 3216) == 0.955


def test_nav_xy_shorter_phone():
    x, y = nav_xy("reels", 1080, 1920)
    assert x == int(1080 * 0.50)
    assert y == int(1920 * 0.965)


def test_reels_candidates_center_first_then_legacy():
    cands = nav_reels_candidates(1440, 3216)
    assert cands[0][2] == 0.50  # x_frac
    assert cands[0][3] == 0.955  # y_frac
    assert any(c[2] == 0.30 for c in cands)
