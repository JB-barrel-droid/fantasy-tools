"""JEG-807: sentinel bands derived from other projection sources (2026-10-22).

Jeremy decision: re-derive the Razzball sentinel floor from current sources each week
instead of the fixed 15.0. Razzball QBs run about 0.83x ESPN as a systematic model
difference (Mahomes 13.8/g vs ESPN 19.2, CBS 22.7). The derived band uses the mean
of the other projection sources multiplied by SENTINEL_LOW_RATIO / SENTINEL_HIGH_RATIO.

Tests:
  (a) Razzball at 0.83x ESPN = pass (systematic model difference, not a scrape error)
  (b) A shifted/garbage value = fail (0, column shift, wrong player)
  (c) Other sources missing = fall back safely and say so (never silently pass,
      never show missing as zero)
"""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import fidelity_pulse as fp  # noqa: E402

NOW = datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc)

# Sentinel player keys (must match PLAYERS list below).
PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 506, "full_name": "Lamar Jackson", "position": "QB", "active": True},
    {"player_key": 3594, "full_name": "Patrick Mahomes", "position": "QB", "active": True},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB", "active": True},
    {"player_key": 1370, "full_name": "Puka Nacua", "position": "WR", "active": True},
    {"player_key": 51, "full_name": "Brock Bowers", "position": "TE", "active": True},
]

# Healthy per-game values at half PPR for building chart fixtures.
GOOD = {869: 21.5, 506: 22.2, 3594: 20.4, 2227: 22.2, 1370: 17.3, 51: 12.2}

# players.json rows with projection PPG data from all three sources.
# Mirrors the live data structure: espn_ppg, cbsros_ppg, rz_ppg as dicts.
PLAYERS_DATA = [
    {"name": "Josh Allen", "player_key": 869, "pos": "QB",
     "espn_ppg": {"standard": 22.0, "half_ppr": 22.0, "ppr": 22.0},
     "cbsros_ppg": {"standard": 24.0, "half_ppr": 24.0, "ppr": 24.0},
     "rz_ppg": {"standard": 18.5, "half_ppr": 18.5, "ppr": 18.5}},
    {"name": "Lamar Jackson", "player_key": 506, "pos": "QB",
     "espn_ppg": {"standard": 22.5, "half_ppr": 22.5, "ppr": 22.5},
     "cbsros_ppg": {"standard": 23.0, "half_ppr": 23.0, "ppr": 23.0},
     "rz_ppg": {"standard": 18.0, "half_ppr": 18.0, "ppr": 18.0}},
    {"name": "Patrick Mahomes", "player_key": 3594, "pos": "QB",
     "espn_ppg": {"standard": 19.22, "half_ppr": 19.22, "ppr": 19.22},
     "cbsros_ppg": {"standard": 22.65, "half_ppr": 22.65, "ppr": 22.65},
     "rz_ppg": {"standard": 13.7, "half_ppr": 13.7, "ppr": 13.7}},
    {"name": "Jahmyr Gibbs", "player_key": 2227, "pos": "RB",
     "espn_ppg": {"standard": 14.5, "half_ppr": 17.8, "ppr": 21.1},
     "cbsros_ppg": {"standard": 15.0, "half_ppr": 18.5, "ppr": 22.0},
     "rz_ppg": {"standard": 14.0, "half_ppr": 17.2, "ppr": 20.4}},
    {"name": "Puka Nacua", "player_key": 1370, "pos": "WR",
     "espn_ppg": {"standard": 10.5, "half_ppr": 14.8, "ppr": 19.1},
     "cbsros_ppg": {"standard": 11.0, "half_ppr": 15.5, "ppr": 20.0},
     "rz_ppg": {"standard": 9.8, "half_ppr": 13.9, "ppr": 18.0}},
    {"name": "Brock Bowers", "player_key": 51, "pos": "TE",
     "espn_ppg": {"standard": 8.0, "half_ppr": 11.0, "ppr": 14.0},
     "cbsros_ppg": {"standard": 9.0, "half_ppr": 12.5, "ppr": 16.0},
     "rz_ppg": {"standard": 7.5, "half_ppr": 10.5, "ppr": 13.5}},
]


def chart(values):
    """Build a chart fixture with half-PPR per-game values."""
    return {"half|1": {k: {"value": v, "text": None, "name": str(k), "pos": None} for k, v in values.items()}}


def validity(source, values, players_data=PLAYERS_DATA):
    """Run stage_scrape_validity with the given chart values and players data."""
    ident = fp.Identity.load(PLAYERS)
    extras = {"players_data": players_data}
    return fp.stage_scrape_validity(source, extras, ident, publisher=None, stored=None, chart=chart(values),
                                    chart_week=None, now=NOW)


class DerivesBandFromOtherSources(unittest.TestCase):
    """The derived band uses the mean of OTHER projection sources' values."""

    def test_derive_mahomes_band_for_razzball(self):
        """When checking razzball, Mahomes band is derived from ESPN + CBS."""
        band = fp._derive_sentinel_band("Patrick Mahomes", "razzball", PLAYERS_DATA)
        self.assertIsNotNone(band)
        lo, hi = band
        # mean(ESPN 19.22, CBS 22.65) = 20.935; lo = 20.935 * 0.55 = 11.51; hi = 20.935 * 1.50 = 31.40
        self.assertAlmostEqual(lo, 20.935 * fp.SENTINEL_LOW_RATIO, places=2)
        self.assertAlmostEqual(hi, 20.935 * fp.SENTINEL_HIGH_RATIO, places=2)

    def test_derive_mahomes_band_for_espn(self):
        """When checking espn, Mahomes band is derived from CBS + Razzball."""
        band = fp._derive_sentinel_band("Patrick Mahomes", "espn", PLAYERS_DATA)
        self.assertIsNotNone(band)
        lo, hi = band
        # mean(CBS 22.65, Razzball 13.7) = 18.175
        self.assertAlmostEqual(lo, 18.175 * fp.SENTINEL_LOW_RATIO, places=2)

    def test_derive_returns_none_when_no_other_sources(self):
        """When no other source has data, derivation returns None (fallback used)."""
        # Only razzball has data for Mahomes.
        sparse = [{"name": "Patrick Mahomes", "player_key": 3594, "pos": "QB",
                    "rz_ppg": {"half_ppr": 13.7}, "espn_ppg": None, "cbsros_ppg": None}]
        band = fp._derive_sentinel_band("Patrick Mahomes", "razzball", sparse)
        self.assertIsNone(band)

    def test_derive_returns_none_when_no_players_data(self):
        self.assertIsNone(fp._derive_sentinel_band("Patrick Mahomes", "razzball", None))
        self.assertIsNone(fp._derive_sentinel_band("Patrick Mahomes", "razzball", []))

    def test_derive_uses_single_source_when_only_one_other(self):
        """When only one other source has data, the band is derived from just that source."""
        sparse = [{"name": "Patrick Mahomes", "player_key": 3594, "pos": "QB",
                    "espn_ppg": {"half_ppr": 19.22}, "cbsros_ppg": None, "rz_ppg": None}]
        band = fp._derive_sentinel_band("Patrick Mahomes", "razzball", sparse)
        self.assertIsNotNone(band)
        lo, hi = band
        self.assertAlmostEqual(lo, 19.22 * fp.SENTINEL_LOW_RATIO, places=2)


class RazzballSystematicDiscount(unittest.TestCase):
    """(a) Razzball at ~0.83x ESPN = pass. The systematic model difference is accepted."""

    def test_razzball_mahomes_at_audit_value_passes(self):
        """Mahomes 13.7 (Razzball) vs ESPN 19.22, CBS 22.65 — documented model difference, not a scrape error."""
        s = validity("razzball", {**GOOD, 3594: 13.7})
        self.assertNotEqual("red", s["status"], s["summary"])
        self.assertEqual([], s["signals"]["sentinel_failures"])

    def test_razzball_mahomes_at_lowest_observed_ratio_passes(self):
        """Mahomes at 0.72x (the lowest observed Rz/ESPN ratio in the audit) passes."""
        # 0.72 * mean(19.22, 22.65) = 0.72 * 20.935 = 15.07
        s = validity("razzball", {**GOOD, 3594: 15.07})
        self.assertNotEqual("red", s["status"], s["summary"])
        self.assertEqual([], s["signals"]["sentinel_failures"])

    def test_razzball_all_qbs_at_083x_pass(self):
        """All sentinel QBs at 0.83x of ESPN+CBS mean should pass."""
        adjusted = dict(GOOD)
        for p in PLAYERS_DATA:
            if p["pos"] == "QB":
                espn_v = p["espn_ppg"]["half_ppr"]
                cbs_v = p["cbsros_ppg"]["half_ppr"]
                ref = (espn_v + cbs_v) / 2
                adjusted[p["player_key"]] = round(ref * 0.83, 1)
        s = validity("razzball", adjusted)
        self.assertNotEqual("red", s["status"], s["summary"])
        self.assertEqual([], s["signals"]["sentinel_failures"])


class GarbageValuesDetected(unittest.TestCase):
    """(b) A shifted/garbage value = fail."""

    def test_zero_value_is_red(self):
        """A sentinel at value 0 (scrape returned empty/zero) is caught."""
        s = validity("razzball", {**GOOD, 3594: 0.0})
        self.assertEqual("red", s["status"])
        names = {b["name"] for b in s["signals"]["sentinel_failures"]}
        self.assertIn("Patrick Mahomes", names)

    def test_column_shift_high_value_is_red(self):
        """A sentinel at 280 (total season points in a per-game field) is caught."""
        s = validity("razzball", {**GOOD, 3594: 280.0})
        self.assertEqual("red", s["status"])
        names = {b["name"] for b in s["signals"]["sentinel_failures"]}
        self.assertIn("Patrick Mahomes", names)

    def test_column_shift_low_value_is_red(self):
        """A sentinel at 3.0 (rushing yards per game in a PPG field) is caught."""
        s = validity("razzball", {**GOOD, 3594: 3.0})
        self.assertEqual("red", s["status"])
        names = {b["name"] for b in s["signals"]["sentinel_failures"]}
        self.assertIn("Patrick Mahomes", names)

    def test_espn_garbage_value_is_red(self):
        """A sentinel at 0 on ESPN is caught, not just Razzball."""
        s = validity("espn", {**GOOD, 3594: 0.0})
        self.assertEqual("red", s["status"])
        names = {b["name"] for b in s["signals"]["sentinel_failures"]}
        self.assertIn("Patrick Mahomes", names)

    def test_multiple_bad_sentinels_all_reported(self):
        """Multiple sentinels outside their bands are all reported."""
        s = validity("razzball", {**GOOD, 3594: 0.0, 506: 0.0})
        self.assertEqual("red", s["status"])
        names = {b["name"] for b in s["signals"]["sentinel_failures"]}
        self.assertEqual({"Patrick Mahomes", "Lamar Jackson"}, names)


class FallbackWhenSourcesMissing(unittest.TestCase):
    """(c) Other sources missing = fall back safely."""

    def test_fallback_band_used_when_no_players_data(self):
        """When players_data is None, the fixed fallback band is used."""
        s = validity("razzball", {**GOOD, 3594: 10.5}, players_data=None)
        self.assertEqual("red", s["status"])
        bad = [b for b in s["signals"]["sentinel_failures"] if b["name"] == "Patrick Mahomes"]
        self.assertEqual(1, len(bad))
        self.assertEqual("fallback", bad[0]["band_source"])

    def test_fallback_band_used_when_player_not_in_data(self):
        """When the sentinel player isn't in players_data, fallback is used."""
        sparse = [{"name": "Someone Else", "player_key": 999, "pos": "QB",
                    "espn_ppg": {"half_ppr": 20.0}}]
        s = validity("razzball", {**GOOD, 3594: 10.5}, players_data=sparse)
        self.assertEqual("red", s["status"])
        bad = [b for b in s["signals"]["sentinel_failures"] if b["name"] == "Patrick Mahomes"]
        self.assertEqual(1, len(bad))
        self.assertEqual("fallback", bad[0]["band_source"])

    def test_fallback_band_used_when_other_sources_are_null(self):
        """When other sources have null PPG, fallback is used."""
        sparse = [{"name": "Patrick Mahomes", "player_key": 3594, "pos": "QB",
                    "rz_ppg": {"half_ppr": 13.7}, "espn_ppg": None, "cbsros_ppg": None}]
        # Use a value inside the fallback band (15.0 to 28.0).
        s = validity("razzball", {**GOOD, 3594: 20.0}, players_data=sparse)
        self.assertNotEqual("red", s["status"])
        # But a value below the fallback floor is caught.
        s2 = validity("razzball", {**GOOD, 3594: 10.0}, players_data=sparse)
        self.assertEqual("red", s2["status"])
        bad = [b for b in s2["signals"]["sentinel_failures"] if b["name"] == "Patrick Mahomes"]
        self.assertEqual("fallback", bad[0]["band_source"])

    def test_derived_band_is_reported_when_used(self):
        """When derivation succeeds, band_source is 'derived'."""
        s = validity("razzball", {**GOOD, 3594: 0.0})
        bad = [b for b in s["signals"]["sentinel_failures"] if b["name"] == "Patrick Mahomes"]
        self.assertEqual(1, len(bad))
        self.assertEqual("derived", bad[0]["band_source"])

    def test_never_silently_passes_missing_data(self):
        """A bad value never silently passes — even without players_data, fallback catches it."""
        for pd in (None, [], [{"name": "Nobody"}]):
            s = validity("razzball", {**GOOD, 3594: 0.0}, players_data=pd)
            self.assertEqual("red", s["status"],
                             f"value 0 should be red with players_data={pd!r}")


class NegativeTests(unittest.TestCase):
    """Prove the sentinel catches work by showing removal lets bad values pass."""

    def test_negative_without_sentinel_call_bad_values_pass(self):
        """With sentinel_failures patched out, a zero value is not caught."""
        with mock.patch.object(fp, "sentinel_failures", return_value=[]):
            s = validity("razzball", {**GOOD, 3594: 0.0})
        self.assertNotEqual("red", s["status"])

    def test_negative_trade_charts_are_not_sentinel_checked(self):
        """Trade chart sources are never sentinel-checked (different scale)."""
        s = validity("usatoday", {**GOOD, 3594: 0.0})
        self.assertEqual([], s["signals"]["sentinel_failures"])


class BackwardsCompatibility(unittest.TestCase):
    """The old test_fidelity_sentinels.py behaviour still holds."""

    def test_healthy_stars_are_green(self):
        for source in ("espn", "cbsros", "razzball"):
            s = validity(source, GOOD)
            self.assertNotEqual("red", s["status"], s)
            self.assertEqual([], s["signals"]["sentinel_failures"])

    def test_a_sentinel_the_chart_does_not_carry_is_not_a_fault(self):
        values = {k: v for k, v in GOOD.items() if k not in (506, 3594)}
        self.assertNotEqual("red", validity("razzball", values)["status"])

    def test_red_scrape_validity_holds_the_source(self):
        s = validity("razzball", {**GOOD, 506: 0.0})
        result = {"stages": {"scrape_validity": s}}
        hold = fp.hold_decision(result, "2026-10-22@x", None, NOW)
        self.assertEqual("fidelity: scrape_validity", hold["reason"])


if __name__ == "__main__":
    unittest.main()
