"""JEG-1171: CBS rest-of-season week-8 divergence warn, traced from stored inputs.

Offline only: reads frozen copies in tests/fixtures/JEG-1171/ (extracted from
git by docs/research/JEG-1171/extract_fixtures.py). No data/raw writes,
Supabase or network. The leave-one-out metric and the two-tier price are
re-implemented here so the expected numbers do not come from the code under
review; the check's own `divergence` is only compared against them.

Pins:
* the published warn (half_12: n 135, outlier 46.7%, bias -2.96) reproduces
  from the frozen values;
* native -> raw -> x scale -> displayed value for five sample players, with the
  Indexed factor at 1.0, and missing kept apart from 0.0;
* the URL, vintage, served week and half/full derivation as stored;
* CBS's nonppr fpts fit 6-pt passing TDs and whole-point yardage per game,
  not the 4-pt fractional scoring the other projection sources use;
* wrong column, wrong week and wrong factor mutations all fail.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "JEG-1171"
sys.path.insert(0, str(REPO / "pipelines"))

import check_source_divergence as sd  # noqa: E402

GROUP = ("espn", "cbsros", "razzball")
SAMPLES = {  # player: (pos, displayed half_12 value)
    "joe burrow": ("QB", 50.4),
    "david montgomery": ("RB", 3.5),
    "jalen coker": ("WR", 6.2),
    "tyler warren": ("TE", 18.0),
    "bijan robinson": ("RB", 49.1),
}


def load(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def keyed(doc: dict, combo: str) -> dict:
    """{source: {player_key: value > 0}} as the check reads it."""
    keys = doc["player_keys"]
    return {s: {int(keys[n]): v for n, v in doc["sources"][s]["combos"][combo].items()
                if n in keys and v and v > 0} for s in GROUP}


def loo(values: dict, source: str) -> tuple[int, float, float]:
    """Independent leave-one-out: (n, outlier_rate, bias) for `source`."""
    devs = []
    for key in set().union(*values.values()):
        priced = {s: values[s][key] for s in values if key in values[s]}
        if len(priced) < 3 or source not in priced:
            continue
        cons = statistics.median(v for s, v in priced.items() if s != source)
        devs.append((priced[source] - cons, cons))
    n = len(devs)
    out = sum(1 for d, c in devs if abs(d) > 0.35 * c and abs(d) >= 2.0)
    return n, round(out / n, 3), round(sum(d for d, _ in devs) / n, 2)


def softplus(z: float) -> float:
    return math.log1p(math.exp(-abs(z))) + max(z, 0.0)


def two_tier_price(x: float, cal: dict) -> float:
    if not x > cal["rw"]:
        return 0.0
    glide = cal["tau"] * (softplus((x - cal["rs"]) / cal["tau"]) - softplus((cal["rw"] - cal["rs"]) / cal["tau"]))
    return cal["pb"] * ((x - cal["rw"]) - glide) + cal["ps"] * glide


def cbs_points(stats: dict, pass_td: float, whole_per_game: bool) -> float:
    g = lambda k: stats.get(k) or 0.0  # noqa: E731
    gp = g("gp") or 1.0

    def yards(total: float, per: float) -> float:
        return gp * math.floor(total / gp / per) if whole_per_game else total / per

    return (yards(g("pass_yds"), 25) + pass_td * g("pass_td") - 2 * g("int")
            + yards(g("rush_yds"), 10) + 6 * g("rush_td")
            + yards(g("rec_yds"), 10) + 6 * g("rec_td") - 2 * g("fl"))


class Reproduce(unittest.TestCase):
    def setUp(self):
        self.doc = load("alert_inputs_e2c191c.json")

    def test_published_warn_reproduces(self):
        pub = self.doc["published_report_cbsros"]
        self.assertEqual((pub["status"], pub["headline_combo"], pub["week"]), ("warn", "half_12", 8))
        for combo, want in (("half_12", (135, 0.467, -2.96)), ("full_12", (134, 0.433, -1.7)),
                            ("standard_12", (132, 0.409, -2.05))):
            values = keyed(self.doc, combo)
            self.assertEqual(loo(values, "cbsros"), want, combo)
            self.assertEqual(want, tuple(pub["combos"][combo][k] for k in ("n", "outlier_rate", "bias")))
            positions = {int(k): p for k, p in self.doc["positions"].items()}
            row = sd.divergence(values, positions)["cbsros"]
            self.assertEqual((row["n"], row["outlier_rate"], row["bias"]), want, combo)
        self.assertGreater(0.467, sd.WARN_OUTLIER_RATE)

    def test_wrong_column_mutation(self):
        # Full-PPR values read as the half column do not give the published half numbers.
        doc = json.loads(json.dumps(self.doc))
        doc["sources"]["cbsros"]["combos"]["half_12"] = doc["sources"]["cbsros"]["combos"]["full_12"]
        self.assertNotEqual(loo(keyed(doc, "half_12"), "cbsros"), (135, 0.467, -2.96))

    def test_wrong_week_mutation(self):
        # The 2026-10-29 rebuild (CBS vintage 2026-10-29) is a different input.
        later = load("later_inputs_ca51f2f.json")
        self.assertEqual(later["sources"]["cbsros"]["vintage"], "2026-10-29")
        self.assertNotEqual(loo(keyed(later, "half_12"), "cbsros"), (135, 0.467, -2.96))


class SourceIdentity(unittest.TestCase):
    def test_url_vintage_and_served_week_as_stored(self):
        doc = load("alert_inputs_e2c191c.json")
        sec = doc["cbsros_section"]
        self.assertTrue(sec["source_url"].endswith("/2026/restofseason/projections/nonppr/"))
        self.assertEqual(sec["week_designated"], "rest of season")
        self.assertEqual(sec["vintage"], "2026-10-26")
        self.assertEqual(sec["lineage"]["raw_built_at"], "2026-10-26T11:51:59Z")
        self.assertEqual(sec["validationHold"]["hold_level"], "amber")
        # The report's "week 8" is the content week; every projection source was
        # served as week-7 data in this build, so the group is not mixed.
        self.assertEqual(doc["content_week"], 8)
        self.assertEqual({s: doc["served"][s]["week"] for s in GROUP}, {"espn": 7, "cbsros": 7, "razzball": 7})
        for s in GROUP:
            self.assertEqual(doc["sources"][s]["week_designated"], "rest of season")  # no weekly/ROS blend

    def test_half_and_full_are_reception_rescores_of_nonppr(self):
        t = load("cbsros_trace_e2c191c.json")["combos"]
        for name in SAMPLES:
            std, half, full = (t[c]["players"][name]["ppg"] for c in ("standard_12", "half_12", "full_12"))
            self.assertAlmostEqual(half, std + 0.5 * (full - std), delta=0.002, msg=name)


class Trace(unittest.TestCase):
    def setUp(self):
        self.trace = load("cbsros_trace_e2c191c.json")["combos"]
        self.alert = load("alert_inputs_e2c191c.json")

    def test_indexed_factor_is_one(self):
        for combo, factors in self.alert["cbsros_index_total"].items():
            self.assertEqual(set(factors.values()), {1.0}, combo)

    def test_native_to_display_for_five_players(self):
        for combo, leg in self.trace.items():
            for name, (pos, shown_half) in SAMPLES.items():
                row = leg["players"][name]
                self.assertEqual(row["pos"], pos)
                self.assertEqual(row["fixture_native"], row["ppg"], (combo, name))
                raw = two_tier_price(row["ppg"], leg["calibration"][pos])
                self.assertAlmostEqual(raw, row["raw_value"], places=9, msg=(combo, name))
                value = raw * leg["scale_70_over_max"] * 1.0  # Indexed factor 1.0
                self.assertEqual(round(value, 1), row["fixture_value"], (combo, name))
                if combo == "half_12":
                    self.assertEqual(row["fixture_value"], shown_half, name)

    def test_wrong_factor_mutation(self):
        leg = self.trace["half_12"]
        moved = [n for n in SAMPLES if round(leg["players"][n]["raw_value"] * leg["scale_70_over_max"] * 1.05, 1)
                 != leg["players"][n]["fixture_value"]]
        self.assertEqual(sorted(moved), sorted(SAMPLES))

    def test_missing_is_not_zero(self):
        leg = self.trace["half_12"]["players"]
        # Rodgers: CBS prices him 0.0 (below its waiver line), present, not missing.
        self.assertEqual((leg["aaron rodgers"]["fixture_value"], leg["aaron rodgers"]["tier"]), (0.0, "waiver"))
        self.assertIn("aaron rodgers", self.alert["sources"]["espn"]["combos"]["half_12"])
        # Chism: CBS has no row at all.
        self.assertIsNone(leg["efton chism iii"]["fixture_native"])
        self.assertIsNone(leg["efton chism iii"]["fixture_value"])
        # The check reads both as "not priced": neither counts toward n.
        values = keyed(self.alert, "half_12")
        for name in ("aaron rodgers", "efton chism iii"):
            self.assertNotIn(int(self.alert["player_keys"][name]), values["cbsros"])


class ScoringBasis(unittest.TestCase):
    """The stored 2026-09-30 raw (the only CBS raw with components in git)."""

    def setUp(self):
        self.rows = load("cbsros_raw_2026-09-30_rows.json")["rows"]

    def test_six_point_td_whole_yards_fits_cbs_fpts(self):
        for r in self.rows:
            got = cbs_points(r["raw_stats"], pass_td=6, whole_per_game=True)
            self.assertLess(abs(got / r["ros_standard"] - 1), 0.06, r["player_name"])

    def test_four_point_fractional_does_not(self):
        # The scoring the ESPN leg uses (pipelines/fidelity_sources/espn.py):
        # QBs come out below CBS fpts, everyone else above.
        for r in self.rows:
            ratio = r["ros_standard"] / cbs_points(r["raw_stats"], pass_td=4, whole_per_game=False)
            if r["pos"] == "QB":
                self.assertGreater(ratio, 1.05, r["player_name"])
            else:
                self.assertLess(ratio, 0.97, r["player_name"])


if __name__ == "__main__":
    unittest.main()
