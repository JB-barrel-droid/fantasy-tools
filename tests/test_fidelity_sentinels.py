"""JEG-592: sentinel stars in the fidelity pulse (class of JEG-555).

Razzball printed Lamar Jackson at 7.1 and Mahomes at 10.5 per game; publisher, stored row and chart all agreed, so
no transport check could see it. A sentinel outside its per-game band on a projection chart turns scrape_validity
red (a holding stage). Negative test: with the sentinel call removed, the seeded bad rows stay green.
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

NOW = datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc)
PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 506, "full_name": "Lamar Jackson", "position": "QB", "active": True},
    {"player_key": 3594, "full_name": "Patrick Mahomes", "position": "QB", "active": True},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB", "active": True},
    {"player_key": 1370, "full_name": "Puka Nacua", "position": "WR", "active": True},
    {"player_key": 51, "full_name": "Brock Bowers", "position": "TE", "active": True},
]
GOOD = {869: 21.5, 506: 22.2, 3594: 20.4, 2227: 22.2, 1370: 17.3, 51: 12.2}


def chart(values):
    return {"half|1": {k: {"value": v, "text": None, "name": str(k), "pos": None} for k, v in values.items()}}


def validity(source, values):
    ident = fp.Identity.load(PLAYERS)
    return fp.stage_scrape_validity(source, {}, ident, publisher=None, stored=None, chart=chart(values),
                                    chart_week=None, now=NOW)


class Sentinels(unittest.TestCase):
    def test_healthy_stars_are_green(self):
        for source in fp.PROJECTIONS:
            s = validity(source, GOOD)
            self.assertNotEqual("red", s["status"], s)
            self.assertEqual([], s["signals"]["sentinel_failures"])

    def test_razzball_lamar_and_mahomes_discount_is_red(self):
        s = validity("razzball", {**GOOD, 506: 7.1, 3594: 10.5})
        self.assertEqual("red", s["status"], s)
        names = {b["name"] for b in s["signals"]["sentinel_failures"]}
        self.assertEqual({"Lamar Jackson", "Patrick Mahomes"}, names)
        self.assertIn("Lamar Jackson 7.1", s["summary"])

    def test_one_per_position_is_checked(self):
        for key, bad in ((2227, 4.0), (1370, 3.0), (51, 2.0), (869, 9.0)):
            s = validity("espn", {**GOOD, key: bad})
            self.assertEqual("red", s["status"], (key, s))

    def test_a_sentinel_the_chart_does_not_carry_is_not_a_fault(self):
        # the bake's outlier guard drops a held number on purpose
        values = {k: v for k, v in GOOD.items() if k not in (506, 3594)}
        self.assertNotEqual("red", validity("razzball", values)["status"])

    def test_a_dropped_value_never_reads_as_zero(self):
        self.assertEqual([], fp.sentinel_failures("razzball", {"half|1": {}}, fp.Identity.load(PLAYERS)))

    def test_trade_charts_are_not_checked_on_the_per_game_scale(self):
        s = validity("usatoday", {**GOOD, 506: 7.1})
        self.assertEqual([], s["signals"]["sentinel_failures"])

    def test_red_scrape_validity_holds_the_source(self):
        s = validity("razzball", {**GOOD, 506: 7.1})
        result = {"stages": {"scrape_validity": s}}
        hold = fp.hold_decision(result, "2026-10-12@x", None, NOW)
        self.assertEqual("fidelity: scrape_validity", hold["reason"])

    def test_negative_without_the_sentinel_call_the_bad_rows_pass(self):
        with mock.patch.object(fp, "sentinel_failures", return_value=[]):
            s = validity("razzball", {**GOOD, 506: 7.1, 3594: 10.5})
        self.assertNotEqual("red", s["status"])


if __name__ == "__main__":
    unittest.main()
