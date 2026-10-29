"""JEG-1172: FantasyPros week-8 divergence trace, offline.

Frozen evidence only: tests/fixtures/JEG-1172/fantasypros-w8-trace.json holds
values copied from committed repo files at e2c191c (the run that raised
divergence:fantasypros:w8) and b863069 (main once the Week 8 article landed),
by docs/research/JEG-1172/extract_fixture.py. No network, Supabase or data/raw.

Pins, with expected numbers calculated here rather than read back from the
reporter: the flagged run served the Week 7 article under a week-8 label (all
178 FantasyPros natives equal frozen week 7), the
scraped column is the one scoring-agnostic base Value, native x the combo's one
Indexed factor equals the shown value for five named players, missing stays
missing and a stored 0 is not a price. Each negative mutation (2QB column,
another combo's factor, the other week's natives, missing read as 0) must break
the trace.
"""
from __future__ import annotations

import json
import statistics
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

import check_source_divergence as sd  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "JEG-1172" / "fantasypros-w8-trace.json"
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
SCORINGS = ("standard", "half", "full")
TOL = 1e-9
# Restated from the JEG-460 rule (not imported) so the expected values are independent.
OUTLIER_REL, OUTLIER_MIN_PTS = 0.35, 2.0


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def trace_breaks(native, factor, shown) -> bool:
    """True when native x factor does not reproduce the shown Indexed value."""
    if native is None or shown is None:
        return (native is None) != (shown is None)
    return abs(native * factor - shown) > TOL


def priced(value) -> float | None:
    """A chart prices a player only above 0; missing and 0 are both unpriced."""
    return value if value is not None and value > 0 else None


def leave_one_out(shown: dict) -> tuple[float, float] | None:
    """(deviation, consensus) for FantasyPros, or None when it is not compared."""
    values = {s: priced(shown[s]) for s in CHARTS}
    values = {s: v for s, v in values.items() if v is not None}
    if "fantasypros" not in values or len(values) < 3:
        return None
    consensus = statistics.median(v for s, v in values.items() if s != "fantasypros")
    return values["fantasypros"] - consensus, consensus


class FantasyProsWeek8Trace(unittest.TestCase):
    def setUp(self):
        self.doc = load()
        self.flagged = self.doc["flagged_run"]
        self.current = self.doc["current_run"]
        self.samples = self.doc["player_names"]["samples"]

    # Source URL, article date and served week
    def test_flagged_run_served_the_week7_article_under_a_week8_label(self):
        fp = self.flagged["sources"]["fantasypros"]
        self.assertEqual(8, self.flagged["content_week"])
        self.assertEqual(7, self.flagged["served"]["fantasypros"]["label_week"])
        self.assertEqual("Week 7", fp["week_designated"])
        self.assertEqual("2026-10-20", fp["content_vintage"])
        self.assertIn("trade-value-chart-week-7-2026", fp["url"])
        # Every chart was still on Week 7, so the run compared Week 7 with Week 7.
        self.assertEqual({7}, {self.flagged["served"][s]["label_week"] for s in CHARTS})
        # The 'also warned in week 7' prior is the same FantasyPros chart.
        self.assertEqual(self.flagged["served"]["fantasypros"]["fingerprint"],
                         self.flagged["history_week7_fantasypros"]["fingerprint"])

    def test_current_run_serves_the_week8_article(self):
        fp = self.current["sources"]["fantasypros"]
        self.assertEqual(8, self.current["content_week"])
        self.assertEqual({8}, {self.current["served"][s]["label_week"] for s in CHARTS})
        self.assertEqual("Week 8", fp["week_designated"])
        self.assertEqual("2026-10-27", fp["content_vintage"])
        self.assertIn("trade-value-chart-week-8-2026", fp["url"])

    # Column
    def test_one_scoring_agnostic_base_value_column(self):
        self.assertIn("base Value is scoring-agnostic", self.flagged["sources"]["fantasypros"]["claimed_settings"])
        for run in (self.flagged, self.current):
            for name in self.samples:
                row = run["players"][name]
                natives = {row["shown"][sc]["fantasypros_native_this_combo"] for sc in SCORINGS}
                self.assertEqual({row["fantasypros_native"]}, natives, name)

    # native -> Indexed -> shown
    def test_native_times_one_factor_is_the_shown_value(self):
        for run in (self.flagged, self.current):
            factors = run["sources"]["fantasypros"]["indexed_factor"]
            for name in self.samples:
                row = run["players"][name]
                self.assertIsNotNone(row["fantasypros_native"], name)
                for sc in SCORINGS:
                    self.assertFalse(trace_breaks(row["fantasypros_native"], factors[sc],
                                                  row["shown"][sc]["fantasypros"]), f"{run['git_rev']} {name} {sc}")

    def test_flagged_natives_are_the_frozen_week7_natives(self):
        week7 = self.flagged["history_week7_fantasypros"]["natives"]
        for name in self.samples:
            for sc in SCORINGS:
                self.assertEqual(week7[name][sc], self.flagged["players"][name]["fantasypros_native"], name)

    def test_whole_flagged_population_is_the_frozen_week7_chart(self):
        pop = self.flagged["population"]
        self.assertEqual([], pop["unkeyed_names"])
        for sc in SCORINGS:
            flagged, week7 = pop["flagged_natives"][sc], pop["history_week7_natives"][sc]
            self.assertEqual(178, len(flagged), sc)
            self.assertEqual(set(week7), set(flagged), sc)
            self.assertEqual([], [k for k in flagged if flagged[k] != week7[k]], sc)
        # Mutation: one changed native is caught.
        mutated = dict(pop["flagged_natives"]["half"])
        first = sorted(mutated)[0]
        mutated[first] += 0.1
        self.assertNotEqual(pop["history_week7_natives"]["half"], mutated)

    def test_independent_consensus_matches_the_recorded_report(self):
        report = self.flagged["report"]["combos"]
        key_of = {n: self.flagged["players"][n]["player_key"] for n in self.samples}
        checked = 0
        for sc in SCORINGS:
            for ex in report[f"{sc}_12"]["examples"]:
                name = next((n for n, k in key_of.items() if k == ex["player_key"]), None)
                if name is None:
                    continue
                dev, consensus = leave_one_out(self.flagged["players"][name]["shown"][sc])
                self.assertAlmostEqual(ex["value"], round(dev + consensus, 1), places=6)
                self.assertAlmostEqual(ex["consensus"], round(consensus, 1), places=6)
                checked += 1
        self.assertGreaterEqual(checked, 3)  # CeeDee Lamb in all three combos

    def test_reporter_math_agrees_on_the_frozen_rows(self):
        """The shared reporter's divergence(), fed the frozen rows, counts the same
        players and the same outliers as the independent calculation."""
        players = self.flagged["players"]
        for sc in SCORINGS:
            values = {s: {} for s in CHARTS}
            for row in players.values():
                for s in CHARTS:
                    v = priced(row["shown"][sc][s])
                    if v is not None and row["player_key"] is not None:
                        values[s][row["player_key"]] = v
            got = sd.divergence(values, {row["player_key"]: row["pos"] for row in players.values()})
            mine = [leave_one_out(players[n]["shown"][sc]) for n in self.samples]
            outliers = sum(1 for d, c in mine if abs(d) > OUTLIER_REL * c and abs(d) >= OUTLIER_MIN_PTS)
            self.assertEqual(len(self.samples), got["fantasypros"]["n"], sc)
            self.assertEqual(outliers, got["fantasypros"]["outliers"], sc)

    # Missing versus zero
    def test_missing_stays_missing_and_zero_is_not_a_price(self):
        adams = self.flagged["players"]["davante adams"]
        wentz = self.flagged["players"]["carson wentz"]
        for sc in SCORINGS:
            self.assertIsNone(adams["shown"][sc]["fantasypros"])
            self.assertEqual(3, sum(1 for s in CHARTS if priced(adams["shown"][sc][s])))
            self.assertIsNone(leave_one_out(adams["shown"][sc]))
            self.assertEqual(0.0, wentz["shown"][sc]["usatoday"])
            self.assertIsNone(priced(wentz["shown"][sc]["usatoday"]))
        self.assertIsNone(adams["fantasypros_native"])

    # Negative mutations
    def test_mutation_2qb_column_breaks_the_trace(self):
        allen = self.flagged["players"]["josh allen"]
        factor = self.flagged["sources"]["fantasypros"]["indexed_factor"]["half"]
        self.assertIsNotNone(allen["fantasypros_native_2qb"])
        self.assertTrue(trace_breaks(allen["fantasypros_native_2qb"], factor, allen["shown"]["half"]["fantasypros"]))

    def test_mutation_other_combo_factor_breaks_the_trace(self):
        factors = self.flagged["sources"]["fantasypros"]["indexed_factor"]
        for name in self.samples:
            row = self.flagged["players"][name]
            for sc in SCORINGS:
                for other in SCORINGS:
                    if other != sc:
                        self.assertTrue(trace_breaks(row["fantasypros_native"], factors[other],
                                                     row["shown"][sc]["fantasypros"]), f"{name} {sc}<-{other}")

    def test_mutation_other_week_natives_break_the_trace(self):
        factors = self.flagged["sources"]["fantasypros"]["indexed_factor"]
        changed = [n for n in self.samples
                   if self.current["players"][n]["fantasypros_native"] != self.flagged["players"][n]["fantasypros_native"]]
        self.assertEqual(["malik nabers", "christian mccaffrey"], changed)
        for name in changed:
            for sc in SCORINGS:
                self.assertTrue(trace_breaks(self.current["players"][name]["fantasypros_native"], factors[sc],
                                             self.flagged["players"][name]["shown"][sc]["fantasypros"]), name)

    def test_mutation_missing_read_as_a_price_is_an_outlier(self):
        adams = dict(self.flagged["players"]["davante adams"]["shown"]["half"])
        adams["fantasypros"] = 0.0
        self.assertIsNone(leave_one_out(adams))  # 0 still is not a price
        adams["fantasypros"] = 1e-9  # missing read as any price: far below the other charts
        dev, consensus = leave_one_out(adams)
        self.assertTrue(abs(dev) > OUTLIER_REL * consensus and abs(dev) >= OUTLIER_MIN_PTS)


if __name__ == "__main__":
    unittest.main()
