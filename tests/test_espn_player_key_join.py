#!/usr/bin/env python3
"""Regression test: ESPN section builder must join leg -> fixture by numeric
player_key, never by name slug.

Bug caught 2026-09-30: build_espn_section_from_ddf_leg.py joined on
player_norm strings. Slug variations ('cameron skattebo' in the leg vs
'cam skattebo' in the fixture; 'travis etienne jr' vs 'travis etienne')
silently dropped players from the ESPN section — the fixture kept stale
values (Skattebo 41.9 vs leg 28.7, Etienne 36.9 vs leg 16.8) because the
fresh values could not map.

The fix: load_leg_values/load_leg_ppg key by player_key, and the section
loop maps player_key -> fixture slug via fixture['player_keys'].
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_espn_section_from_ddf_leg import load_leg_values, load_leg_ppg


def test_leg_loaders_key_by_player_key():
    """Leg loaders must return player_key-keyed dicts, not name-keyed."""
    legs = sorted((REPO / "data" / "ddf-two-tier").glob("*/ddf_leg.json"))
    assert legs, "no DDF legs found"
    # Use the half_ppr leg (has the known problem players)
    leg_path = next(p for p in legs if "-espn-half_ppr-" in p.parent.name)
    vals = load_leg_values(leg_path)
    ppgs = load_leg_ppg(leg_path)
    # Keys must be ints (player_key), not strings
    assert all(isinstance(k, int) for k in vals), "values not keyed by int player_key"
    assert all(isinstance(k, int) for k in ppgs), "ppgs not keyed by int player_key"
    # Known slug-variation players must be present by key
    assert 3664 in vals, "cameron skattebo (key 3664) missing from leg values"
    assert 810 in vals, "travis etienne jr (key 810) missing from leg values"
    print("PASS: leg loaders key by numeric player_key")


def test_slug_variations_resolve_via_player_key():
    """The exact slug pairs that broke must resolve to the same player_key
    in the fixture's player_keys registry."""
    fixture = json.loads(
        (REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json")
        .read_text()
    )
    player_keys = fixture.get("player_keys", {})
    # leg slug -> fixture slug -> both must map to the same numeric key
    pairs = [
        ("cameron skattebo", "cam skattebo", 3664),
        ("travis etienne jr", "travis etienne", 810),
    ]
    for leg_slug, fixture_slug, expected_key in pairs:
        fkey = player_keys.get(fixture_slug)
        assert fkey is not None, f"fixture slug {fixture_slug!r} not in player_keys"
        assert int(fkey) == expected_key, (
            f"{fixture_slug!r} maps to {fkey}, expected {expected_key}"
        )
    print("PASS: slug variations resolve to the same player_key")


def test_fixture_espn_section_matches_leg():
    """The built fixture ESPN section must carry fresh leg values for the
    previously-dropped players (no stale values)."""
    fixture = json.loads(
        (REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json")
        .read_text()
    )
    half = fixture["sources"]["espn"]["combos"]["half_12"]["values"]
    # Skattebo: leg 28.7 (was stale 41.9); Etienne: leg 16.8 (was stale 36.9)
    assert abs(half.get("cam skattebo", -1) - 28.7) < 0.1, (
        f"cam skattebo fixture={half.get('cam skattebo')}, expected ~28.7"
    )
    assert abs(half.get("travis etienne", -1) - 16.8) < 0.1, (
        f"travis etienne fixture={half.get('travis etienne')}, expected ~16.8"
    )
    # Achane (IR, not in leg) must have NO ESPN value, not a stale 54.9
    assert "devon achane" not in half or not half["devon achane"], (
        "IR player devon achane should have no ESPN fixture value"
    )
    print("PASS: fixture ESPN section carries fresh leg values")


if __name__ == "__main__":
    test_leg_loaders_key_by_player_key()
    test_slug_variations_resolve_via_player_key()
    test_fixture_espn_section_matches_leg()
    print("All ESPN player_key join tests passed.")
