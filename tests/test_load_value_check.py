"""JEG-479 item 5: the rows the chain stores in public.value_check_values.

Both sides of every compared value, keyed (season, week, scoring, teams,
roster, view, series, player_key); `agrees` uses the report's tolerance with
exact presence; `held` marks every series of a held root; the DDF Value's
prior-week sides are stored as series <version>_prior.
"""
from __future__ import annotations

import csv
import gzip
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import load_value_check as lv  # noqa: E402


def _setting(engine_vals, ref_vals, prior_e=None, prior_r=None):
    spec = {"scoring": "half_ppr", "teams": 10, "superflex": 1}
    reference = {"half_ppr/10/sf1": {"setting": spec, "views": {"indexed": {"7": ref_vals}, "vorp": {}, "adj": {}},
                                     "prior": {"indexed": {"ddf_value": {"values": prior_r or {}}}}}}
    engine = {"half_ppr/10/sf1": {"views": {"indexed": {"7": engine_vals}, "vorp": {}, "adj": {}},
                                  "prior": {"indexed": {"ddf_value": {"values": prior_e or {}}}}}}
    return engine, reference


class LoadValueCheckRows(unittest.TestCase):
    def test_rows(self):
        engine, reference = _setting({"espn": 10.0, "cbs": 5.0, "ddf_value": 7.0, "razzball": None},
                                     {"espn": 10.04, "cbs": 5.2, "ddf_value": 7.0, "razzball": 3.0},
                                     {"7": 6.0}, {"7": 6.0})
        rows = lv.build_rows({"tolerance": 0.05}, engine, reference, 2026, 5, {7: "some player"},
                             {"cbs", "cbs_adjusted"})
        by = {r["series"]: r for r in rows}
        self.assertEqual(set(by), {"espn", "cbs", "ddf_value", "razzball", "ddf_value_prior"})
        self.assertTrue(by["espn"]["agrees"])
        self.assertFalse(by["cbs"]["agrees"])
        self.assertTrue(by["cbs"]["held"])
        self.assertFalse(by["espn"]["held"])
        self.assertFalse(by["razzball"]["agrees"], "presence must match exactly")
        self.assertIsNone(by["razzball"]["engine_value"])
        self.assertEqual(by["ddf_value_prior"]["engine_value"], 6.0)
        r = by["espn"]
        self.assertEqual((r["season"], r["week"], r["scoring"], r["teams"], r["roster"], r["view"], r["player"]),
                         (2026, 5, "half", 10, "superflex", "indexed", "some player"))

    def test_player_names_prefer_the_lowercased_name(self):
        fixture = {"player_keys": {"ja'marr chase": 1, "jamarr chase": 1, "x": 2}}
        players = {1: {"name": "Ja'Marr Chase"}, 2: {"name": "Somebody"}, 3: {"name": "No Slug"}}
        self.assertEqual(lv.player_names(fixture, players), {1: "ja'marr chase", 2: "x", 3: "no slug"})


class FakeSb:
    """Counts every HTTP call the loader would make."""

    def __init__(self):
        self.calls = []

    def post(self, table, body, params="", prefer=""):
        self.calls.append(("POST", table, len(body)))
        return [{"run_id": "run-1"}]

    def delete(self, table, params=""):
        self.calls.append(("DELETE", table, 0))


def _many_rows(n, n_bad):
    rows = []
    for i in range(n):
        bad = i < n_bad
        rows.append({"season": 2026, "week": 7, "scoring": "full", "teams": 12, "roster": "standard",
                     "view": "indexed", "series": "espn", "player_key": i, "player": f"p{i}",
                     "engine_value": 10.0 + (i % 50 if bad else 0), "reference_value": 10.0,
                     "agrees": not bad, "held": False})
    return rows


class PersistenceIsBounded(unittest.TestCase):
    """JEG-792 (Jeremy 2026-10-21, 'Self-host on the Mac mini'): the log is one
    artifact plus a summary row; the database sees only bounded mismatches."""

    def test_http_calls_do_not_grow_with_values(self):
        for n, n_bad in ((2_000, 0), (60_000, 3), (60_000, 5_000)):
            rows = _many_rows(n, n_bad)
            sb = FakeSb()
            lv.store(sb, {"generated_at": "2026-10-21T00:00:00Z"}, lv.mismatches(rows), 2026, 7, n)
            self.assertLessEqual(len(sb.calls), 4, (n, n_bad, sb.calls))
            stored = sum(c[2] for c in sb.calls if c[1] == "value_check_values" and c[0] == "POST")
            self.assertLessEqual(stored, lv.MAX_MISMATCH_ROWS)
            self.assertEqual(stored, min(n_bad, lv.MAX_MISMATCH_ROWS))

    def test_mismatches_are_worst_first_and_never_include_agreeing_rows(self):
        rows = _many_rows(1_000, 700)
        rows.append({**rows[0], "player_key": 99_999, "engine_value": None, "agrees": False})
        bad = lv.mismatches(rows)
        self.assertEqual(len(bad), lv.MAX_MISMATCH_ROWS)
        self.assertTrue(all(not r["agrees"] for r in bad))
        self.assertEqual(bad[0]["player_key"], 99_999, "a presence mismatch outranks a numeric gap")

    def test_artifact_holds_every_value(self):
        rows = _many_rows(3_000, 700)
        with tempfile.TemporaryDirectory() as d:
            path = lv.write_artifact(rows, Path(d) / "v.csv.gz")
            with gzip.open(path, "rt", encoding="utf-8", newline="") as fh:
                back = list(csv.DictReader(fh))
        self.assertEqual(len(back), 3_000)
        self.assertEqual(sum(1 for r in back if r["agrees"] == "False"), 700)
        self.assertEqual(list(back[0]), lv.CSV_COLUMNS)


if __name__ == "__main__":
    unittest.main()
