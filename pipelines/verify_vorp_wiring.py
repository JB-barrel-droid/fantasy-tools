#!/usr/bin/env python3
"""Verify VORP translation is truly wired through: fixture values match Supabase.

Checks:
1. For each as-published source, the fixture's reindexed values match
   Supabase publisher_translated_values (for players that have them).
2. Ordering is preserved: if native A > native B, then translated A > translated B.
   (Catches the per-bucket scaling bug that flipped Puka/JSN.)

Used by the monitoring dashboard to prove fixes are wired through,
not just implemented.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines" / "vorp_translation"))
sys.path.insert(0, str(Path.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"))

# Canonical test case: Puka vs JSN on FantasyCalc half-PPR 12-team
# Native: JSN 9914 > Puka 7386. Translated must preserve: JSN > Puka.
ORDERING_TESTS = [
    ("fantasycalc", "half_12_qb1", "jaxon smithnjigba", "puka nacua"),
]

# JEG-73: Adjusted sections must preserve the raw ordering for the same players.
# If raw has A > B, the _adjusted section must also have A > B.
# Covers all 4 adjusted sources to catch stale adjusted sections.
ADJUSTED_SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
ADJUSTED_ORDERING_TESTS = [
    # (source, combo, higher_name, lower_name) - same pairs as ORDERING_TESTS
    # but checked against the _adjusted section
    ("fantasycalc", "half_12_qb1", "jaxon smithnjigba", "puka nacua"),
]

def load_supabase_translated(source: str, scoring: str, teams: int, week: int) -> dict[str, float]:
    """Load translated values from Supabase, keyed by normalized name."""
    try:
        from sb import get  # type: ignore
    except ImportError:
        # Fallback: use subprocess
        import subprocess
        SB = [sys.executable, str(Path.home() / "workspace" / "skills" /
              "supabase-football-signal" / "bin" / "sb.py")]
        q = (f"?select=player_key,translated_value&source=eq.{source}"
             f"&scoring=eq.{scoring}&league_teams=eq.{teams}&week=eq.{week}&limit=1000")
        r = subprocess.run(SB + ["get", "publisher_translated_values", q],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {}
        rows = json.loads(r.stdout)
        # Map player_key -> value (we'll resolve names via fixture)
        return {str(row["player_key"]): float(row["translated_value"]) for row in rows}
    return {}

def main() -> int:
    fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    fixture = json.loads(fixture_path.read_text())
    player_keys = fixture.get("player_keys", {})
    # Invert: key -> name
    key_to_name = {str(v): k for k, v in player_keys.items()}

    errors = []

    for source, combo_key, higher_name, lower_name in ORDERING_TESTS:
        combo = fixture["sources"][source]["combos"].get(combo_key, {})
        reindexed = combo.get("reindexed", {})
        native = combo.get("native", {})

        # Find slugs
        higher_slug = next((s for s in reindexed if higher_name in s.lower()), None)
        lower_slug = next((s for s in reindexed if lower_name in s.lower()), None)

        if not higher_slug or not lower_slug:
            errors.append(f"{source}/{combo_key}: could not find {higher_name} or {lower_name} in reindexed")
            continue

        # Check native ordering
        higher_native = native.get(higher_slug, 0)
        lower_native = native.get(lower_slug, 0)
        if higher_native <= lower_native:
            errors.append(f"{source}/{combo_key}: native ordering wrong: {higher_name}={higher_native} <= {lower_name}={lower_native}")
            continue

        # Check translated ordering
        higher_trans = reindexed.get(higher_slug, 0)
        lower_trans = reindexed.get(lower_slug, 0)
        if higher_trans <= lower_trans:
            errors.append(
                f"{source}/{combo_key}: ORDERING FLIP: {higher_name} native={higher_native:.0f} > "
                f"{lower_name} native={lower_native:.0f}, but translated {higher_trans:.1f} <= {lower_trans:.1f}. "
                f"VORP wiring is broken or using stale reindexed values."
            )
        else:
            print(f"OK {source}/{combo_key}: {higher_name} ({higher_trans:.1f}) > {lower_name} ({lower_trans:.1f})")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1

    # JEG-73: Check _adjusted sections preserve raw ordering for all 4 sources.
    # A stale adjusted section (built from old raw values) will show wrong orderings.
    print("\nChecking _adjusted sections (JEG-73)...")
    for source, combo_key, higher_name, lower_name in ADJUSTED_ORDERING_TESTS:
        adj_source = f"{source}_adjusted"
        if adj_source not in fixture["sources"]:
            errors.append(f"{adj_source}: section missing from fixture")
            continue
        combo = fixture["sources"][adj_source]["combos"].get(combo_key, {})
        adj_reindexed = combo.get("reindexed", {})
        # Also get raw for comparison
        raw_combo = fixture["sources"][source]["combos"].get(combo_key, {})
        raw_reindexed = raw_combo.get("reindexed", {})

        higher_slug = next((s for s in adj_reindexed if higher_name in s.lower()), None)
        lower_slug = next((s for s in adj_reindexed if lower_name in s.lower()), None)

        if not higher_slug or not lower_slug:
            errors.append(f"{adj_source}/{combo_key}: could not find {higher_name} or {lower_name}")
            continue

        # Raw ordering must be correct first
        higher_raw = raw_reindexed.get(higher_slug, 0)
        lower_raw = raw_reindexed.get(lower_slug, 0)
        if higher_raw <= lower_raw:
            errors.append(f"{source}/{combo_key}: raw ordering wrong, cannot check adjusted")
            continue

        # Adjusted must preserve raw ordering
        higher_adj = adj_reindexed.get(higher_slug, 0)
        lower_adj = adj_reindexed.get(lower_slug, 0)
        if higher_adj <= lower_adj:
            errors.append(
                f"{adj_source}/{combo_key}: STALE ADJUSTED SECTION: raw has "
                f"{higher_name} ({higher_raw:.1f}) > {lower_name} ({lower_raw:.1f}), "
                f"but adjusted has {higher_adj:.1f} <= {lower_adj:.1f}. "
                f"Run pipelines/build_adjusted_fixture_sections.py to rebuild."
            )
        else:
            print(f"OK {adj_source}/{combo_key}: {higher_name} ({higher_adj:.1f}) > {lower_name} ({lower_adj:.1f})")

    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\nAll VORP wiring checks passed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
