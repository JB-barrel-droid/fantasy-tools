"""Short published charts: waiver line extrapolated from the other charts.

V2-WAIVER-COVERAGE, Jeremy 2026-10-07: "If needed for computations, cover them
by extrapolating from the average of other charts. Denote them. Where it's not
needed, hide those values."

When a chart lists no more players at a position than the league rosters, its
waiver line used to be its LAST listed value (insufficient_coverage), so the
bottom of a short chart was 0 only because the list ended. Now the chart is
extended with imputed natives from the other published charts
(unified.impute_extension / ValueModel.imputeExtension) and the line is read at
the rostered count. Imputed players never get a value.

Checks here (the server translation, pipelines/vorp_translation/unified.py):
  * the imputation arithmetic, by hand, on a synthetic chart;
  * a short position prices its last listed player; without peers it did not
    (the old behaviour) -- this is the test that fails on the old code;
  * no usable peer -> the old fallback, denoted insufficient_coverage;
  * a chart that is never short translates exactly as before;
  * imputed players never appear as the chart's values;
  * (JEG-482 removed the saved-fixture checks: the saved Indexed values are
    no longer this translation.)
  * JEG-702 (Jeremy 2026-10-16, Q1: "Both: point the checks at the live
    engine and retire the unused code."): the browser port
    (ValueModel.imputeExtension / translatePublishedVorp) had no caller on
    the page and was removed, with its Python == JS parity and mutation
    checks. The Python translation keeps the checks above.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

from pipelines.vorp_translation import unified  # noqa: E402

FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
SCORINGS = ("standard", "half_ppr", "ppr")


def _load_ranked(source, scoring):
    ranked, key_by_name = unified.load_native_values(source, scoring, 12)
    return {pos: [(key_by_name[unified.norm_player_name(n)], n, v) for n, v in rows]
            for pos, rows in ranked.items()}


def _load_peers(source, scoring):
    """V2-WAIVER-COVERAGE: the other published charts' saved natives, keyed."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return unified.peers_ranked(unified.peer_natives(fixture, source, scoring))


def _keyed(prefix, values, start=0):
    return [(f"{prefix}{i}", f"{prefix} {i}", float(v)) for i, v in enumerate(values, start)]


# A chart listing 6 QBs / 12 RBs (a 12-team league rosters ~21 / ~55) whose
# bottom half is also on two peer charts in other units, plus players it omits.
THIN_CHART = {"QB": _keyed("q", [30, 25, 20, 15, 10, 8]),
              "RB": _keyed("r", [60, 50, 45, 40, 35, 30, 25, 20, 18, 16, 14, 12]),
              "WR": _keyed("w", range(200, 20, -2)), "TE": _keyed("t", range(60, 20, -1))}
THIN_PEERS = {
    "peer_a": {"QB": _keyed("q", [300, 250, 200, 150, 100, 80] + list(range(78, 0, -3))),
               "RB": _keyed("r", [600, 500, 450, 400, 350, 300, 250, 200, 180, 160, 140, 120]
                            + list(range(118, 0, -2)))},
    "peer_b": {"QB": _keyed("q", [60, 50, 40, 30, 20, 16, 15.5, 15, 14, 9, 8, 7, 6, 5, 4, 3, 2, 1,
                                  0.5, 0.4, 0.3, 0.2, 0.1, 0.05, 0.01])},
}
NO_COVER_PEERS = {"peer_a": {"QB": _keyed("q", [5, 4, 3], start=40),
                             "RB": _keyed("r", [9, 8], start=4) + _keyed("r", [7, 6, 5], start=90)}}


def _pairs(by_pos):
    return {pos: [(k, v) for k, _n, v in rows] for pos, rows in by_pos.items()}


def _thin(peers, teams=12):
    return unified.translate_ranked(THIN_CHART, teams, peers=peers)


class ImputationArithmetic(unittest.TestCase):
    def test_extension_by_hand(self):
        ext = unified.impute_extension(_pairs(THIN_CHART), THIN_PEERS)
        # Bottom half of the chart's QBs (<= its median 15): q3 15, q4 10, q5 8.
        # peer_a: 150+100+80 -> k = 33/330 = 0.1; peer_b: 30+20+16 -> k = 33/66 = 0.5.
        # q6: mean(0.1 x 78, 0.5 x 15.5) = 7.775 (below the chart's last QB, 8).
        first = ext["QB"][0]
        self.assertEqual(first[0], "q6")
        self.assertAlmostEqual(first[1], (0.1 * 78 + 0.5 * 15.5) / 2, places=12)
        for pos, rows in ext.items():
            last = THIN_CHART[pos][-1][2]
            self.assertTrue(all(v <= last for _k, v in rows), f"{pos}: imputed above last listed")
            self.assertEqual([v for _k, v in rows], sorted((v for _k, v in rows), reverse=True))
            listed = {k for k, _n, _v in THIN_CHART[pos]}
            self.assertFalse(listed & {k for k, _v in rows}, f"{pos}: a listed player was imputed")

    def test_capped_at_last_listed(self):
        # A peer that values an omitted player far above the chart's bottom:
        # the chart left him out, so he is worth at most its last listed value.
        chart = {"TE": [("a", "a", 30.0), ("b", "b", 20.0), ("c", "c", 10.0), ("d", "d", 5.0),
                        ("e", "e", 4.0), ("f", "f", 3.0)]}
        peer = {"p": {"TE": [("a", "a", 30.0), ("c", "c", 10.0), ("d", "d", 5.0), ("e", "e", 4.0),
                             ("f", "f", 3.0), ("x", "x", 25.0), ("y", "y", 1.0)]}}
        ext = unified.impute_extension(_pairs(chart), peer)
        self.assertEqual(ext["TE"], [("x", 3.0), ("y", 1.0)])


class ShortChartTranslation(unittest.TestCase):
    def test_short_position_prices_last_listed_player(self):
        """The bug: q5 (the chart's last QB) is 0 only because the list ended."""
        old = _thin(None)
        new = _thin(THIN_PEERS)
        self.assertEqual(old["positions"]["QB"]["waiver_method"], "insufficient_coverage")
        self.assertNotIn("q5", old["translated"])
        qb = new["positions"]["QB"]
        self.assertEqual(qb["waiver_method"], unified.WAIVER_IMPUTED)
        self.assertEqual(qb["n_listed"], 6)
        self.assertEqual(qb["n_imputed"], qb["n_rostered"] - 6 + 1)
        ext = unified.impute_extension(_pairs(THIN_CHART), THIN_PEERS)["QB"]
        self.assertEqual(qb["waiver_line_value"], round(ext[qb["n_rostered"] - 6][1], 2))
        self.assertGreater(new["translated"]["q5"]["translated"], 0)
        # RB is covered too (peer_a lists 59 more RBs).
        self.assertEqual(new["positions"]["RB"]["waiver_method"], unified.WAIVER_IMPUTED)
        self.assertIn("r11", new["translated"])
        self.assertNotIn("r11", old["translated"])

    def test_imputed_players_never_get_values(self):
        new = _thin(THIN_PEERS)
        listed = {k for rows in THIN_CHART.values() for k, _n, _v in rows}
        self.assertLessEqual(set(new["translated"]), listed)

    def test_no_peer_coverage_keeps_old_fallback(self):
        new = _thin(NO_COVER_PEERS)
        old = _thin(None)
        for pos in ("QB", "RB"):
            self.assertEqual(new["positions"][pos]["waiver_method"], "insufficient_coverage", pos)
            self.assertEqual(new["positions"][pos]["waiver_line_value"],
                             round(THIN_CHART[pos][-1][2], 2), pos)
        self.assertEqual(new["translated"], old["translated"])

    def test_chart_never_short_is_unchanged(self):
        """USA Today and FantasyCalc at 12 teams list more players than the
        league rosters at every position: peers change nothing."""
        for source in ("usatoday", "fantasycalc"):
            for scoring in SCORINGS:
                ranked = _load_ranked(source, scoring)
                with_peers = unified.translate_ranked(ranked, 12, peers=_load_peers(source, scoring))
                without = unified.translate_ranked(ranked, 12)
                self.assertEqual(with_peers, without, f"{source}/{scoring}")
                self.assertTrue(all(p["waiver_method"] == "roster_determined"
                                    for p in with_peers["positions"].values()))

    def test_real_short_charts_are_extrapolated(self):
        """CBS lists 12 QBs, ~43 RBs, ~44 WRs, ~17 TEs: every position short at
        12 teams. Its last listed QB (Matthew Stafford in Week 5) was 0."""
        for scoring in SCORINGS:
            ranked = _load_ranked("cbs", scoring)
            out = unified.translate_ranked(ranked, 12, peers=_load_peers("cbs", scoring))
            for pos, p in out["positions"].items():
                self.assertEqual(p["waiver_method"], unified.WAIVER_IMPUTED, f"cbs/{scoring}/{pos}")
                self.assertLessEqual(p["waiver_line_value"], ranked[pos][-1][2])
            last_qb = ranked["QB"][-1][0]
            self.assertIn(last_qb, out["translated"], f"cbs/{scoring}: last listed QB still 0")


if __name__ == "__main__":
    unittest.main()
