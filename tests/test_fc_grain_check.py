#!/usr/bin/env python3
"""JEG-705: regression tests for fc_grain_check (column-swap detection).

Negative-tested: a genuine column swap is caught; drift on a stale bake is not.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from fidelity_pulse import fc_grain_check, FC_GRAIN_CHECK_MAX_AGE_S


def _make_grains(values: dict[str, dict[int, float]]) -> dict:
    """values: {grain: {player_key: value}}."""
    return {
        g: {k: {"value": v, "text": None, "name": f"player_{k}", "pos": "WR"}
            for k, v in players.items()}
        for g, players in values.items()
    }


# Realistic FantasyCalc-like data: 50 players, full > half > std by ~1% each.
_PLAYERS = list(range(1, 51))
_BASE = {k: 5000 + k * 100 for k in _PLAYERS}


def _scoring_set(base: dict[int, float], full_bump: float = 50, half_bump: float = 25) -> dict[str, dict[int, float]]:
    """Three scorings per QB group, with small scoring gaps."""
    return {
        "std|1": {k: v for k, v in base.items()},
        "half|1": {k: v + half_bump for k, v in base.items()},
        "full|1": {k: v + full_bump for k, v in base.items()},
        "std|2": {k: v - 100 for k, v in base.items()},
        "half|2": {k: v - 100 + half_bump for k, v in base.items()},
        "full|2": {k: v - 100 + full_bump for k, v in base.items()},
    }


class TestGenuineSwapDetected:
    """A real column swap (full stored as half, half as std) must be caught."""

    def test_swap_detected_on_fresh_bake(self):
        live = _make_grains(_scoring_set(_BASE))
        # Swap: stored "full" actually holds half data, stored "half" holds std data
        swapped_vals = _scoring_set(_BASE)
        stored_vals = dict(swapped_vals)
        stored_vals["full|1"] = swapped_vals["half|1"]
        stored_vals["half|1"] = swapped_vals["std|1"]
        stored_vals["std|1"] = swapped_vals["full|1"]
        stored = _make_grains(stored_vals)
        problems = fc_grain_check(live, stored, bake_age_s=60)  # 1 minute old
        assert len(problems) > 0, "a genuine column swap must be detected on a fresh bake"
        # The message should name the swapped grains
        assert any("full|1" in p for p in problems)

    def test_swap_detected_when_age_unknown(self):
        """When bake_age_s is None (unknown), the check still runs."""
        live = _make_grains(_scoring_set(_BASE))
        swapped_vals = _scoring_set(_BASE)
        stored_vals = dict(swapped_vals)
        stored_vals["full|2"] = swapped_vals["half|2"]
        stored_vals["half|2"] = swapped_vals["std|2"]
        stored_vals["std|2"] = swapped_vals["full|2"]
        stored = _make_grains(stored_vals)
        problems = fc_grain_check(live, stored, bake_age_s=None)
        assert len(problems) > 0, "a genuine swap must be detected even when bake age is unknown"


class TestFalsePositiveOnStaleBake:
    """JEG-705: drift on a stale bake must NOT trigger a false-positive swap."""

    def test_drift_exceeding_scoring_gap_skipped_on_stale_bake(self):
        """When the bake is old and values drifted more than the scoring gap,
        the check must NOT fire."""
        live_vals = _scoring_set(_BASE)
        # Stored values are from 3 hours ago; values have drifted UP by 40 points
        # (more than the 25-point half bump or 50-point full bump scoring gap)
        stored_vals = {g: {k: v - 40 for k, v in players.items()}
                       for g, players in _scoring_set(_BASE).items()}
        live = _make_grains(live_vals)
        stored = _make_grains(stored_vals)
        # On a stale bake (> FC_GRAIN_CHECK_MAX_AGE_S), the check is skipped
        problems = fc_grain_check(live, stored, bake_age_s=FC_GRAIN_CHECK_MAX_AGE_S + 1)
        assert problems == [], (
            f"a stale bake must not trigger a column-swap false positive: {problems}"
        )

    def test_drift_does_trigger_on_fresh_bake_when_genuine(self):
        """Verify the negative test: a genuine swap on a fresh bake is still caught."""
        swapped_vals = _scoring_set(_BASE)
        stored_vals = dict(swapped_vals)
        stored_vals["full|1"] = swapped_vals["half|1"]
        stored_vals["half|1"] = swapped_vals["std|1"]
        stored_vals["std|1"] = swapped_vals["full|1"]
        live = _make_grains(_scoring_set(_BASE))
        stored = _make_grains(stored_vals)
        # Fresh bake: swap IS detected
        problems_fresh = fc_grain_check(live, stored, bake_age_s=60)
        assert len(problems_fresh) > 0, "fresh bake with a swap must be caught"
        # Stale bake: swap is NOT checked (skipped entirely)
        problems_stale = fc_grain_check(live, stored, bake_age_s=FC_GRAIN_CHECK_MAX_AGE_S + 1)
        assert problems_stale == [], "stale bake skips the check even if data is genuinely swapped"


class TestNoSwapOnCorrectData:
    """Correct data must never trigger the check."""

    def test_identical_data(self):
        vals = _scoring_set(_BASE)
        grains = _make_grains(vals)
        assert fc_grain_check(grains, grains, bake_age_s=0) == []

    def test_small_drift_no_swap(self):
        """Small drift (within scoring gap) on a fresh bake is fine."""
        live_vals = _scoring_set(_BASE)
        stored_vals = {g: {k: v - 5 for k, v in players.items()}
                       for g, players in _scoring_set(_BASE).items()}
        live = _make_grains(live_vals)
        stored = _make_grains(stored_vals)
        assert fc_grain_check(live, stored, bake_age_s=300) == []
