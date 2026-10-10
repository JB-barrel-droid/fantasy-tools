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

Checks here (the parity of the whole translation, peers included, on every
real chart and setting lives in tests/test_vorp_translation_js_parity.py):
  * the imputation arithmetic, by hand, on a synthetic chart;
  * a short position prices its last listed player; without peers it did not
    (the old behaviour) -- this is the test that fails on the old code;
  * no usable peer -> the old fallback, denoted insufficient_coverage;
  * a chart that is never short translates exactly as before;
  * imputed players never appear as the chart's values;
  * Python == JS for imputeExtension, real and synthetic, bit for bit;
  * (JEG-482 removed the saved-fixture checks: the saved Indexed values are
    no longer this translation; it is the VORP vs waivers view's math);
  * mutations of the JS port (cap dropped, fit on the whole list, peers
    ignored, sum instead of mean) are caught.
"""
from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_vorp_translation_js_parity import (
    DRIVER, FIXTURE, NO_COVER_PEERS, SCORINGS, SOURCES, THIN_CHART, THIN_PEERS, VALUE_MODEL,
    _load_peers, _load_ranked, _python, _real_vectors, run_parity,
)
from pipelines.vorp_translation import unified


def _pairs(by_pos):
    return {pos: [(k, v) for k, _n, v in rows] for pos, rows in by_pos.items()}


def _thin(peers, teams=12):
    return unified.translate_ranked(THIN_CHART, teams, peers=peers)


def _js_impute(vectors, model_path=VALUE_MODEL):
    payload = {"vectors": [{
        "kind": "impute",
        "ranked": {pos: [[r[0], r[-1]] for r in rows] for pos, rows in v["ranked_keyed"].items()},
        "peers": {src: {pos: [[r[0], r[-1]] for r in rows] for pos, rows in by_pos.items()}
                  for src, by_pos in (v.get("peers") or {}).items()},
    } for v in vectors]}
    proc = subprocess.run(["node", str(DRIVER), str(model_path)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr[:2000]}")
    return [{pos: [tuple(r) for r in rows] for pos, rows in res["extension"].items()}
            for res in json.loads(proc.stdout)["results"]]


def _py_impute(vector):
    ranked = {pos: sorted(((str(r[0]), float(r[-1])) for r in rows), key=lambda r: -r[1])
              for pos, rows in vector["ranked_keyed"].items()}
    out = unified.impute_extension(ranked, vector.get("peers"))
    return {pos: [tuple(r) for r in rows] for pos, rows in out.items()}


def _impute_vectors():
    vectors = [{"label": "thin", "ranked_keyed": THIN_CHART, "peers": THIN_PEERS},
               {"label": "no-cover", "ranked_keyed": THIN_CHART, "peers": NO_COVER_PEERS}]
    for source in SOURCES:
        for scoring in SCORINGS:
            vectors.append({"label": f"{source}/{scoring}", "ranked_keyed": _load_ranked(source, scoring),
                            "peers": _load_peers(source, scoring)})
    return vectors


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


class ImputationParity(unittest.TestCase):
    def test_js_equals_python_impute_extension(self):
        vectors = _impute_vectors()
        js = _js_impute(vectors)
        n = 0
        for vec, got in zip(vectors, js):
            want = _py_impute(vec)
            self.assertEqual(want, got, vec["label"])
            n += sum(len(rows) for rows in want.values())
        print(f"\n[V2-WAIVER-COVERAGE impute parity] vectors={len(vectors)} imputed_rows={n}")
        self.assertGreater(n, 500)

    def test_guard_catches_broken_ports(self):
        source = VALUE_MODEL.read_text(encoding="utf-8")
        mutations = {
            "no-cap": ("Math.min(last, slot[0] / slot[1])", "slot[0] / slot[1]"),
            "fit-whole-list": ("return Number(p.value) <= median;", "return true;"),
            "sum-not-mean": ("Math.min(last, slot[0] / slot[1])", "Math.min(last, slot[0])"),
            "peers-ignored": ("var extension = opts.peers ? imputeExtension(ranked, opts.peers) : {};",
                              "var extension = {};"),
            "waiver-at-list-end": ("if (nRostered < players.length) method = \"roster_determined\";",
                                   "if (true) { method = \"roster_determined\"; waiverVal = players[players.length - 1].value; }"),
        }
        vectors = [v for v in _real_vectors() if v["source"] == "cbs" and v["scoring"] == "ppr"
                   and v["bench_per_team"] in (3, 6) and v["flex_count"] == 1]
        vectors += [{"label": "thin-peers", "ranked_keyed": THIN_CHART, "peers": THIN_PEERS,
                     "teams": 12, "bench_per_team": 6, "flex_count": 1, "slots": None,
                     "flex_eligible": None}]
        with tempfile.TemporaryDirectory() as tmp:
            intact = Path(tmp) / "value-model-intact.js"
            intact.write_text(source)
            self.assertEqual(run_parity(vectors, intact)[0], [])
            for name, (old, new) in mutations.items():
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name} moved")
                broken = Path(tmp) / f"value-model-{name}.js"
                broken.write_text(source.replace(old, new))
                failures = run_parity(vectors, broken)[0]
                print(f"\n[V2-WAIVER-COVERAGE negative test] {name}: {len(failures)} failing vectors")
                self.assertGreater(len(failures), 0, f"mutation {name} was NOT caught")


if __name__ == "__main__":
    unittest.main()
