"""JEG-480 fidelity pulse, USA Today: every published player is stored.

Found by the pulse on 2026-10-09 (ops-alert #425): 8 players on the week-5
article were never stored (Tyreek Hill 15, Austin Ekeler, Joshua Palmer,
Darius Slayton, Tyler Goodson, Carson Wentz, Jaydon Blue, Zach Ertz). The
saver resolved them, then dropped every row the save-time reindex could not
pair with an ESPN anchor value -- native value included -- so the chain,
which prices from native_value, never saw the publisher's number. It also
resolved names with the legacy matcher instead of lib/canonical_players
(JEG-438), and its identity misses reached identity_queue only from main(),
which the CI ingest never calls.

Hermetic: no network, no Supabase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "ops" / "watchdog"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


saver_base = _load("save_espn_cbs_references", ROOT / "pipelines" / "save_espn_cbs_references.py")
usat = _load("save_usatoday_references", ROOT / "pipelines" / "save_usatoday_references.py")
importer = _load("import_supabase_references_jeg480", ROOT / "pipelines" / "import_supabase_references.py")


class _NoAudit:
    def __init__(self, *a, **k):
        self.run_id = "t"

    def start(self):
        return self.run_id

    def complete(self, row_count):
        pass

    def fail(self, msg):
        pass

    def audit_rows(self, rows):
        return rows


PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 7001, "full_name": "Michael Smith", "position": "WR", "active": True},
]
PULL = {
    "url": "https://www.usatoday.com/story/sports/fantasy/football/2026/10/06/x-week-5-ros-rankings/1/",
    "fetched_at": "2026-10-08",
    "tables": [
        {"title": "Quarterback trade value chart", "headers": ["RK", "Player", "1QB"],
         "rows": [["1", "Josh Allen", "36"]]},
        {"title": "Wide receiver trade value chart", "headers": ["RK", "Player", "STD", "Half", "PPR"],
         # "Mike" is the players row "Michael": the canonical nickname rule
         # resolves him; the legacy matcher did not.
         "rows": [["1", "Mike Smith", "20", "21", "22"],
                  ["2", "Nobody Known", "5", "5", "5"]]},
    ],
}


class SaverTest(unittest.TestCase):
    def setUp(self):
        self.writes = []
        self.queued = []
        patches = [
            mock.patch.object(usat, "fetch_players", lambda: PLAYERS),
            mock.patch.object(usat, "upsert_rows", lambda t, rows, c: self.writes.append(rows)),
            mock.patch.object(usat, "count_rows", lambda t, p: sum(len(r) for r in self.writes)),
            mock.patch.object(usat, "WriterAudit", _NoAudit),
        ]
        import identity_queue
        patches.append(mock.patch.object(identity_queue, "record_misses",
                                         lambda src, review: self.queued.append((src, review))))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.path = Path(tempfile.mkdtemp()) / "usat.json"
        self.path.write_text(json.dumps(PULL), encoding="utf-8")

    def _rows_without_anchor(self, clean):
        """apply_reindex with a reindex that prices only Josh Allen."""
        def fake_reindex(path):
            cand = json.loads(Path(path).read_text(encoding="utf-8"))
            combos = {c: {"reindexed": {s: 99.0 for s in body["native"] if s == "josh allen"}}
                      for c, body in cand["combos"].items()}
            return {"combos": combos}, []
        import reindex_comparison_section
        with mock.patch.object(reindex_comparison_section, "reindex_section", fake_reindex):
            return usat.apply_reindex(clean, [], "b")

    def test_names_resolve_through_canonical_players(self):
        clean, review, _, _ = usat.build_usatoday_rows(self.path, 5, "b")
        self.assertEqual({r["player_key"] for r in clean}, {869, 7001})
        self.assertEqual({r["name"] for r in review}, {"Nobody Known"})

    def test_a_row_without_an_anchor_pair_is_stored_with_its_native_value(self):
        clean, _, _, _ = usat.build_usatoday_rows(self.path, 5, "b")
        final, review = self._rows_without_anchor(clean)
        smith = [r for r in final if r["player_key"] == 7001]
        self.assertEqual(len(smith), 3)
        self.assertTrue(all(r["value"] is None for r in smith))
        self.assertEqual(sorted(r["native_value"] for r in smith), [20.0, 21.0, 22.0])
        self.assertTrue(all(r["value"] == 99.0 for r in final if r["player_key"] == 869))
        self.assertTrue(any("no ESPN anchor pair" in r["reason"] for r in review))

    def test_identity_misses_are_queued_by_the_save_the_ingest_calls(self):
        with mock.patch.object(usat, "apply_reindex", lambda c, r, b: (c, r)):
            usat.save_usatoday(self.path, dry_run=False, week=5, bake_id="b")
        self.assertEqual(len(self.queued), 1)
        src, review = self.queued[0]
        self.assertEqual(src, "usatoday")
        import identity_queue
        self.assertEqual([m["name"] for m in identity_queue.identity_misses(review)], ["Nobody Known"])


class ImporterTest(unittest.TestCase):
    def test_usatoday_row_without_chart_value_is_priced_by_native(self):
        row = {"value": None, "native_value": 15.0, "player_key": 3081}
        self.assertEqual(importer.native_priced("usatoday", row)["value"], 15.0)

    def test_fantasycalc_row_without_chart_value_is_priced_by_native(self):
        # JEG-512: save_fantasycalc_references shares usatoday's apply_reindex,
        # so it stores the same NULL-value rows (Tyreek Hill, 2026-10-09 bake).
        row = {"value": None, "native_value": 357.0, "player_key": 3081}
        self.assertEqual(importer.native_priced("fantasycalc", row)["value"], 357.0)

    def test_other_sources_keep_the_strict_rule(self):
        row = {"value": None, "native_value": 15.0}
        self.assertIsNone(importer.native_priced("cbs", row)["value"])

    def test_no_native_value_stays_missing(self):
        row = {"value": None, "native_value": None}
        self.assertIsNone(importer.native_priced("usatoday", row)["value"])


if __name__ == "__main__":
    unittest.main()
