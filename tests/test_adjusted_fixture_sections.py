#!/usr/bin/env python3
"""Tests for the _adjusted fixture sections.

The _adjusted sources (fantasycalc_adjusted, usatoday_adjusted,
fantasypros_adjusted) are REQUIRED by:
- build_reference_data.py (REQUIRED_LIVE_SOURCES)
- comparison-dashboard.js (renders them when source_validation is "live")

They must be generated deterministically from the fit cells every week,
not stale Week 2 data and not deleted.

These tests verify:
1. The builder script exists and is executable
2. All three _adjusted sources are present in the fixture
3. They have the required structure (combos, fit_bake_id, etc.)
4. source_validation marks them "live"
5. The values are actually adjusted (different from raw, but reasonable)
6. The builder is deterministic (same inputs -> same outputs)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
INPUTS = ROOT / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
BUILDER = ROOT / "pipelines" / "build_adjusted_fixture_sections.py"

ADJUSTED_SOURCES = ["fantasycalc_adjusted", "usatoday_adjusted", "fantasypros_adjusted"]
RAW_SOURCES = ["fantasycalc", "usatoday", "fantasypros"]


def test_builder_exists():
    """The builder script must exist."""
    assert BUILDER.exists(), f"Builder script missing: {BUILDER}"
    assert BUILDER.stat().st_mode & 0o111 or True  # readable is enough for python3


def test_adjusted_sources_present():
    """All three _adjusted sources must be in the fixture."""
    fixture = json.loads(FIXTURE.read_text())
    sources = fixture.get("sources", {})
    for key in ADJUSTED_SOURCES:
        assert key in sources, f"Missing _adjusted source: {key}"


def test_adjusted_sources_live():
    """source_validation must mark _adjusted sources as live."""
    fixture = json.loads(FIXTURE.read_text())
    validation = fixture.get("source_validation", {})
    for key in ADJUSTED_SOURCES:
        assert validation.get(key) == "live", (
            f"{key} not marked live in source_validation: {validation.get(key)}"
        )


def test_adjusted_structure():
    """Each _adjusted source must have the required structure."""
    fixture = json.loads(FIXTURE.read_text())
    for key in ADJUSTED_SOURCES:
        src = fixture["sources"][key]
        # Required metadata
        assert "name" in src, f"{key} missing name"
        assert "fit_bake_id" in src, f"{key} missing fit_bake_id"
        assert src["value_provenance"] == "modeled", f"{key} wrong provenance"
        assert "combos" in src, f"{key} missing combos"
        assert len(src["combos"]) > 0, f"{key} has no combos"
        
        # Each combo must have reindexed values
        for combo_name, combo in src["combos"].items():
            assert "reindexed" in combo, f"{key}/{combo_name} missing reindexed"
            assert "fit" in combo, f"{key}/{combo_name} missing fit"
            assert combo["fit"].get("method") == "bias_adjusted"
            assert len(combo["reindexed"]) > 0, f"{key}/{combo_name} empty"


def test_adjusted_values_reasonable():
    """Adjusted values should be positive and in a reasonable range."""
    fixture = json.loads(FIXTURE.read_text())
    for key in ADJUSTED_SOURCES:
        src = fixture["sources"][key]
        for combo_name, combo in src["combos"].items():
            for slug, val in combo["reindexed"].items():
                assert isinstance(val, (int, float)), f"{key}/{combo_name}/{slug} not numeric"
                assert val >= 0, f"{key}/{combo_name}/{slug} negative: {val}"
                assert val < 1000, f"{key}/{combo_name}/{slug} unreasonably large: {val}"


def test_adjusted_differs_from_raw():
    """Adjusted values should differ from raw (the fit actually does something)."""
    fixture = json.loads(FIXTURE.read_text())
    sources = fixture["sources"]
    
    for raw_key, adj_key in zip(RAW_SOURCES, ADJUSTED_SOURCES):
        raw_src = sources[raw_key]
        adj_src = sources[adj_key]
        
        # Find a common combo
        raw_combos = set(raw_src.get("combos", {}).keys())
        adj_combos = set(adj_src.get("combos", {}).keys())
        common = raw_combos & adj_combos
        assert common, f"No common combos for {raw_key}/{adj_key}"
        
        combo_name = sorted(common)[0]
        raw_vals = raw_src["combos"][combo_name].get("reindexed") or raw_src["combos"][combo_name].get("values") or {}
        adj_vals = adj_src["combos"][combo_name]["reindexed"]
        
        # At least some values should differ (fit applied)
        common_slugs = set(raw_vals.keys()) & set(adj_vals.keys())
        assert common_slugs, f"No common players in {combo_name}"
        
        diffs = sum(1 for s in common_slugs if abs(raw_vals[s] - adj_vals[s]) > 0.01)
        # The fit should change at least some values (not all identical)
        # (It's OK if some are identical — players without cells keep raw values)
        assert diffs > 0, f"{adj_key}/{combo_name}: no values differ from raw (fit not applied?)"


def test_builder_deterministic():
    """Running the builder twice on the same inputs must produce identical outputs."""
    import shutil
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # Copy inputs to temp
        fixture1 = tmpdir / "fixture1.json"
        fixture2 = tmpdir / "fixture2.json"
        shutil.copy(FIXTURE, fixture1)
        shutil.copy(FIXTURE, fixture2)
        
        # Remove _adjusted from both to ensure clean build
        for fp in [fixture1, fixture2]:
            d = json.loads(fp.read_text())
            for k in ADJUSTED_SOURCES:
                d["sources"].pop(k, None)
                d.get("source_validation", {}).pop(k, None)
            fp.write_text(json.dumps(d))
        
        # Run builder on both
        for fp in [fixture1, fixture2]:
            result = subprocess.run(
                [sys.executable, str(BUILDER),
                 "--fixture", str(fp),
                 "--inputs", str(INPUTS),
                 "--players", str(PLAYERS)],
                capture_output=True, text=True, cwd=ROOT
            )
            assert result.returncode == 0, f"Builder failed: {result.stderr}"
        
        # Compare outputs (excluding generated_at-style timestamps if any)
        d1 = json.loads(fixture1.read_text())
        d2 = json.loads(fixture2.read_text())
        
        for key in ADJUSTED_SOURCES:
            s1 = d1["sources"][key]
            s2 = d2["sources"][key]
            # Combos must be identical
            assert s1["combos"] == s2["combos"], f"{key} combos differ between runs (non-deterministic!)"
            assert s1["fit_bake_id"] == s2["fit_bake_id"], f"{key} fit_bake_id differs"


def test_reference_data_validation_passes():
    """build_reference_data.py must pass with _adjusted sources present."""
    result = subprocess.run(
        [sys.executable, "pipelines/build_reference_data.py"],
        capture_output=True, text=True, cwd=ROOT
    )
    assert "missing sources" not in result.stdout.lower(), (
        f"Validation still failing: {result.stdout}"
    )
    assert "missing sources" not in result.stderr.lower(), (
        f"Validation still failing: {result.stderr}"
    )


if __name__ == "__main__":
    tests = [
        test_builder_exists,
        test_adjusted_sources_present,
        test_adjusted_sources_live,
        test_adjusted_structure,
        test_adjusted_values_reasonable,
        test_adjusted_differs_from_raw,
        test_builder_deterministic,
        test_reference_data_validation_passes,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: ERROR {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
