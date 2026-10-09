"""GAP-RAZZBALL-CHART-BEHIND-STORED (JEG-480 fidelity pulse, 2026-10-09).

Razzball re-saved snapshot date 2026-10-08 in place at 03:25 UTC with new
numbers (Josh Jacobs 5.9 -> 0.1 PPR per game). The upsert landed, then the
saver failed its count check (690 rows vs 688 saved: Kaytron Allen and Emari
Demercado were left over from the 19:26 save). The upsert never moved the
rows' `_written_at`, so the pulse read the last write as 23:25 and called the
chart's 23:27 stamp "newer than the data it holds". The chain imported all
690 rows, the two left-over players included, under the new snapshot id.

Pinned here, each with the broken state it names:
  1. The chain holds Razzball when the values it would serve (section natives,
     players.json rz_ppg) are not the values of the snapshot their id names:
     a stale bake / section stamped with the new id never publishes.
  2. One snapshot date = one save: the import drops rows from an earlier
     save of the date (players the publisher dropped since).
  3. The saver stamps `_written_at` on every write and checks its own save
     landed whole, not that the date holds nothing else.
  4. The pulse reads a row's write time from the save, and ignores
     superseded rows.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import projection_identity as pid  # noqa: E402
import rebuild_comparison_chain as chain  # noqa: E402
from latest_save import latest_save_rows  # noqa: E402
from test_rebuild_chain_failclosed import WireFake, make_repo, simulate_bake  # noqa: E402
from test_razzball_supabase import PLAYERS, importer, saver, write_snapshot  # noqa: E402

JACOBS, LLOYD = 1095, 3364


def rz_row(key, norm, std, half, ppr):
    return {"player_key": key, "player_name": norm.title(), "player_norm": norm, "pos": "RB",
            "rz_std_ppg": std, "rz_half_ppr_ppg": half, "rz_ppr_ppg": ppr}


SAVE_2325 = [rz_row(JACOBS, "josh jacobs", 4.8, 5.3, 5.9), rz_row(LLOYD, "marshawn lloyd", 7.3, 8.5, 9.7)]
SAVE_0325 = [rz_row(JACOBS, "josh jacobs", 0.1, 0.1, 0.1), rz_row(LLOYD, "marshawn lloyd", 10.4, 12.1, 13.8)]


def section_for(rows):
    by_col = {"standard": "rz_std_ppg", "half": "rz_half_ppr_ppg", "full": "rz_ppr_ppg"}
    combos = {f"{s}_{t}": {"native": {r["player_norm"]: r[col] for r in rows},
                           "values": {r["player_norm"]: 10.0 for r in rows}}
              for s, col in by_col.items() for t in (8, 10, 12, 14)}
    return combos


def players_for(rows):
    return [{"player_key": r["player_key"], "name": r["player_name"],
             "rz_ppg": {"standard": r["rz_std_ppg"], "half_ppr": r["rz_half_ppr_ppg"],
                        "ppr": r["rz_ppr_ppg"]}} for r in rows]


class StaleValuesUnderNewStamp(unittest.TestCase):
    """The incident's shape: the snapshot is the 03:25 save; what would be
    served carries the 03:25 id but the 23:25 numbers."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rz-one-save-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _repo(self, tag, section_rows, baked_rows):
        repo = make_repo(self.tmp / tag, tuple(chain.SOURCES))
        snap = chain.find_latest_snapshot(repo, "razzball")
        snap.write_text(json.dumps({"vintage_date": "2026-09-29", "rows": SAVE_0325}))
        players = repo / chain.PLAYERS_REL
        doc = json.loads(players.read_text(encoding="utf-8"))
        doc["players"] = players_for(baked_rows)
        players.write_text(json.dumps(doc))
        simulate_bake(repo)  # stamps rz_snapshot_id = the 03:25 snapshot's id
        kept = {"vintage": "2026-09-29", "snapshot_id": "sha256:old", "combos": section_for(SAVE_2325)}
        (repo / chain.FIXTURE_REL).write_text(json.dumps({
            "player_keys": {r["player_norm"]: r["player_key"] for r in SAVE_0325},
            "sources": {"razzball": kept}}))
        return repo, snap, kept, section_rows

    def _fake(self, repo, section_rows):
        class Fake(WireFake):
            def __call__(self, cmd, **kw):
                ok, out = super().__call__(cmd, **kw)
                if Path(cmd[1]).name == "build_razzball_section_from_ddf_leg.py":
                    path = self.repo / chain.FIXTURE_REL
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    doc["sources"]["razzball"]["combos"] = section_for(section_rows)
                    doc["player_keys"] = {r["player_norm"]: r["player_key"] for r in SAVE_0325}
                    path.write_text(json.dumps(doc))
                return ok, out
        return Fake(repo)

    def test_coherent_values_publish(self):
        repo, snap, _, rows = self._repo("ok", SAVE_0325, SAVE_0325)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=self._fake(repo, rows))
        self.assertNotIn("razzball", status["held"], status["detail"])
        self.assertIsNone(chain.razzball_values_mismatch(repo, snap))

    def test_stale_section_with_the_new_stamp_is_held(self):
        repo, snap, kept, rows = self._repo("section", SAVE_2325, SAVE_0325)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=self._fake(repo, rows))
        self.assertIn("razzball", status["held"])
        detail = status["detail"]["razzball"]
        self.assertEqual("review", detail["failed_stage"])
        self.assertIn("josh jacobs", detail["detail"])
        fixture = json.loads((repo / chain.FIXTURE_REL).read_text(encoding="utf-8"))
        # The stale candidate is never what the fixture publishes.
        published = (fixture.get("sources") or {}).get("razzball") or {}
        self.assertNotEqual(section_for(SAVE_2325), published.get("combos"))

    def test_stale_bake_with_the_new_stamp_is_held(self):
        repo, snap, _, rows = self._repo("bake", SAVE_0325, SAVE_2325)
        # The ids agree (that is all the identity gate can see) ...
        self.assertEqual(pid.file_id(snap), pid.players_ids(repo / chain.PLAYERS_REL)["razzball"])
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=self._fake(repo, rows))
        self.assertIn("razzball", status["held"])
        self.assertIn("players.json Josh Jacobs", status["detail"]["razzball"]["detail"])

    def test_without_the_values_gate_the_stale_section_publishes(self):
        # The broken state (origin/main): only ids are compared.
        repo, _, kept, rows = self._repo("nogate", SAVE_2325, SAVE_0325)
        with mock.patch.object(chain, "razzball_values_mismatch", return_value=None, create=True):
            status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=self._fake(repo, rows))
        self.assertNotIn("razzball", status["held"])

    def test_a_served_player_missing_from_the_snapshot_is_held(self):
        gone = SAVE_0325 + [rz_row(4700, "kaytron allen", 2.4, 2.6, 2.9)]
        repo, _, _, rows = self._repo("gone", SAVE_0325, gone)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=self._fake(repo, rows))
        self.assertIn("razzball", status["held"])
        self.assertIn("Kaytron Allen: not in snapshot", status["detail"]["razzball"]["detail"])


class OneSnapshotDateIsOneSave(unittest.TestCase):
    def test_latest_save_rows(self):
        rows = [{"player_key": 1, "pulled_at": "2026-10-09T03:25:30.1+00:00"},
                {"player_key": 2, "pulled_at": "2026-10-09T03:25:30.1+00:00"},
                {"player_key": 3, "pulled_at": "2026-10-08T19:26:52.4+00:00"}]
        keep, dropped = latest_save_rows(rows)
        self.assertEqual([1, 2], [r["player_key"] for r in keep])
        self.assertEqual([3], [r["player_key"] for r in dropped])
        legacy = [{"player_key": 1}, {"player_key": 2}]
        self.assertEqual((legacy, []), latest_save_rows(legacy))

    def test_import_drops_rows_left_from_an_earlier_save_of_the_date(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        saver.fetch_players = lambda: PLAYERS
        try:
            rows, _, _ = saver.build_razzball_rows(write_snapshot(tmp.name))
        finally:
            saver.fetch_players = saver._default_fetch_players
        allen, gibbs = sorted(rows, key=lambda r: r["player_key"])
        allen["pulled_at"] = allen["_written_at"] = "2026-10-01T19:26:52+00:00"  # earlier save
        saved = (importer.fetch_supabase_rows, importer.fetch_player_names,
                 importer.fetch_player_positions, importer.fixture_pos_team)
        self.addCleanup(lambda: (setattr(importer, "fetch_supabase_rows", saved[0]),
                                 setattr(importer, "fetch_player_names", saved[1]),
                                 setattr(importer, "fetch_player_positions", saved[2]),
                                 setattr(importer, "fixture_pos_team", saved[3])))
        importer.fetch_supabase_rows = lambda table, params: [allen, gibbs]
        importer.fetch_player_names = lambda keys: {869: "Josh Allen", 2227: "Jahmyr Gibbs"}
        importer.fetch_player_positions = lambda keys: {869: "QB", 2227: "RB"}
        importer.fixture_pos_team = lambda: {869: ("QB", "BUF"), 2227: ("RB", "DET")}
        result = importer.import_source("razzball", output_dir=Path(tmp.name) / "sources")
        snap = json.loads(result["snapshot_path"].read_text(encoding="utf-8"))
        self.assertEqual(["Jahmyr Gibbs"], [r["player_name"] for r in snap["rows"]])
        self.assertEqual([869], [r["player_key"] for r in snap["superseded_rows"]])


class ImportHealthCountsTheNewestSave(unittest.TestCase):
    """Chain run 37939612502 (first run with the import fix): the snapshot held
    688 rows, the health check counted all 690 of the date and failed it
    TABLE_DRIFT."""

    def test_rows_left_from_an_earlier_save_are_not_drift(self):
        from datetime import date
        import test_import_health as ih
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        saved = ih.mod.fetch_table_summary
        self.addCleanup(setattr, ih.mod, "fetch_table_summary", saved)

        def table(name, params):
            self.assertIn("pulled_at", params)
            rows = ih.db_rows(10, source_content_date="2026-09-21", date_col="razzball_snapshot_date")
            for r in rows:
                r["pulled_at"] = "2026-09-21T03:25:30+00:00"
            old = ih.db_rows(2, source_content_date="2026-09-21", date_col="razzball_snapshot_date")
            for i, r in enumerate(old):
                r.update(player_key=5000 + i, pulled_at="2026-09-20T19:26:52+00:00")
            return rows + old
        ih.mod.fetch_table_summary = table
        root = Path(tmp.name)
        ih.make_snapshot(root, "razzball", "2026-09-21", content_vintage="2026-09-21",
                         week_designated=None, supabase_table="public.razzball_projections")
        entry, _ = ih.mod.verify_source("razzball", sources_root=root, nfl_week=3,
                                        check_date=date(2026, 9, 21), prev_entry=None, checked_at="t")
        self.assertEqual("ok", entry["status"], entry.get("failure_reason"))
        self.assertEqual(10, entry["db_latest_rows"])
        self.assertEqual(2, entry["ignored_older_rows"])


class SaverStampsAndChecksItsOwnSave(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        saved = (saver.fetch_players, saver.upsert_rows, saver.count_rows)
        self.addCleanup(lambda: (setattr(saver, "fetch_players", saved[0]),
                                 setattr(saver, "upsert_rows", saved[1]),
                                 setattr(saver, "count_rows", saved[2])))
        saver.fetch_players = lambda: PLAYERS

    def test_every_row_stamps_its_write_time(self):
        rows, _, _ = saver.build_razzball_rows(write_snapshot(self.tmp.name))
        self.assertTrue(all(r["_written_at"] == r["pulled_at"] for r in rows))

    def _main(self, table_rows_for):
        written, queries = [], []
        saver.upsert_rows = lambda table, rows, conflict: written.extend(rows)

        def count(table, params):
            queries.append(params)
            return table_rows_for(params, written)
        saver.count_rows = count
        argv = sys.argv
        sys.argv = ["save", "--snapshot", str(write_snapshot(self.tmp.name))]
        try:
            saver.main()
        finally:
            sys.argv = argv
        return queries

    def test_rows_left_from_an_earlier_save_do_not_fail_the_save(self):
        # The table holds this save's 2 rows plus 1 from an earlier save.
        def table(params, written):
            return len(written) if "pulled_at=eq." in params else len(written) + 1
        queries = self._main(table)
        own = [q for q in queries if "pulled_at=eq." in q]
        self.assertEqual(1, len(own))
        self.assertNotIn("+", own[0])  # the stamp is URL-encoded

    def test_a_save_that_did_not_land_whole_still_fails_closed(self):
        with self.assertRaises(SystemExit) as ctx:
            self._main(lambda params, written: len(written) - 1)
        self.assertIn("from this save", str(ctx.exception))


class PulseReadsTheSave(unittest.TestCase):
    def setUp(self):
        import fidelity_pulse
        from fidelity_sources import razzball
        self.pulse, self.mod = fidelity_pulse, razzball

    def test_an_in_place_resave_reads_as_written_at_its_save(self):
        row = {"player_key": JACOBS, "_written_at": "2026-10-08T19:26:52+00:00",
               "pulled_at": "2026-10-09T03:25:30+00:00"}
        self.assertEqual("2026-10-09T03:25:30Z", self.pulse.iso(self.pulse.written_at(row)))

    def test_superseded_rows_are_not_the_stored_snapshot(self):
        rows = [{"player_key": JACOBS, "pulled_at": "2026-10-09T03:25:30+00:00"},
                {"player_key": 4700, "pulled_at": "2026-10-08T19:26:52+00:00"}]
        self.assertEqual([JACOBS], [r["player_key"] for r in self.pulse.dedupe_snapshot(rows, self.mod)])
        self.assertIn("pulled_at", self.mod.STORED_SELECT)


if __name__ == "__main__":
    unittest.main()
