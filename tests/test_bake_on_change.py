"""GAP-BAKE-ON-CHANGE (2026-10-08): players.json and the projection sections
are built from one snapshot, checked by content id, not by date.

Incident: the change probe dispatched a CBS ROS scrape at 13:53 UTC; it
re-saved cbs_snapshot_date 2026-10-08 (first saved 08:48) with new numbers.
The chain rebuilt the CBS ROS section from the 13:54 rows while players.json
(the browser's CBS ROS / Razzball / ESPN pricing) was baked at 11:45 from the
08:48 rows. tests.test_cbsros_8t_qb failed in every combo and nothing
published until the next daily bake. Both carried the date 2026-10-08, so no
date check could tell them apart.

Pinned here, each negative-tested against the broken state it names:
  1. projection_identity: a same-date snapshot with one changed value is a
     different snapshot; row order is not.
  2. The chain holds (isolated) a projection source whose input differs from
     players.json's baked id -- the old section is kept, the others publish.
  3. The chain holds a source whose built section carries another id.
  4. The chain bakes on change: decide() says bake when any projection input
     differs from players.json (and on the forced daily run).
  5. Section builders refuse legs from two snapshots.
  6. The committed fixture: every projection section matches players.json
     (id when both carry one, else the older date keys) and players.json's
     ESPN id is the committed ESPN CSV.
  7. bake-players.yml (manual) bakes from the chain's inputs, not a re-export.
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
sys.path.insert(0, str(ROOT / "tests"))

import projection_identity as pid  # noqa: E402
import rebuild_comparison_chain as chain  # noqa: E402
from test_rebuild_chain_failclosed import WireFake, make_repo, simulate_bake  # noqa: E402

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
ESPN_CSV = ROOT / "data" / "inputs" / "espn_projections.csv"

ROWS_0848 = [{"player_key": 869, "pos": "QB", "per_game_ppr": 22.1},
             {"player_key": 1095, "pos": "RB", "per_game_ppr": 17.4}]
ROWS_1354 = [{"player_key": 869, "pos": "QB", "per_game_ppr": 22.6},  # re-projected
             {"player_key": 1095, "pos": "RB", "per_game_ppr": 17.4}]


class SnapshotIdentity(unittest.TestCase):
    def test_same_date_resave_is_a_different_snapshot(self):
        a = pid.snapshot_doc_id({"vintage_date": "2026-10-08", "rows": ROWS_0848})
        b = pid.snapshot_doc_id({"vintage_date": "2026-10-08", "rows": ROWS_1354})
        self.assertNotEqual(a, b)

    def test_row_order_is_not_a_different_snapshot(self):
        a = pid.snapshot_doc_id({"vintage_date": "2026-10-08", "rows": ROWS_0848})
        b = pid.snapshot_doc_id({"vintage_date": "2026-10-08", "rows": ROWS_0848[::-1]})
        self.assertEqual(a, b)

    def test_espn_id_is_the_legs_csv_sha(self):
        # The ESPN legs record inputs.espn_csv_sha256; the section turns it
        # into snapshot_id, and the bake records file_id(csv). One value.
        import hashlib
        sha = hashlib.sha256(ESPN_CSV.read_bytes()).hexdigest()
        self.assertEqual(pid.file_id(ESPN_CSV), pid.espn_id_from_sha256(sha))


class ChainHoldsOnIdentity(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bake-on-change-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _repo(self, tag):
        repo = make_repo(self.tmp / tag, tuple(chain.SOURCES))
        snap = chain.find_latest_snapshot(repo, "cbsros")
        # WireFake's section builder stamps vintage 2026-09-29.
        snap.write_text(json.dumps({"vintage_date": "2026-09-29", "rows": ROWS_0848}))
        simulate_bake(repo)  # players.json baked from the 08:48 save
        kept = {"vintage": "2026-10-08", "combos": {"full_12": {"values": {"x": 1.0}}}}
        (repo / chain.FIXTURE_REL).write_text(json.dumps({"sources": {"cbsros": kept}}))
        return repo, snap, kept

    def _resave_1354(self, snap):
        snap.write_text(json.dumps({"vintage_date": "2026-09-29", "rows": ROWS_1354}))

    def test_coherent_inputs_publish_every_projection_source(self):
        repo, _, _ = self._repo("ok")
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=WireFake(repo))
        self.assertEqual([], status["held"], status["detail"])
        self.assertTrue(status["success"], status["failed"])

    def test_same_date_resave_holds_cbsros_and_keeps_its_section(self):
        repo, snap, kept = self._repo("resave")
        self._resave_1354(snap)
        fake = WireFake(repo)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=fake)
        self.assertEqual(["cbsros"], status["held"])
        self.assertTrue(status["success"], status["failed"])
        self.assertIn("awaiting players bake", status["detail"]["cbsros"]["detail"])
        self.assertNotIn("build_cbsros_ddf_leg.py", fake.calls)
        fixture = json.loads((repo / chain.FIXTURE_REL).read_text())
        self.assertEqual(kept, fixture["sources"]["cbsros"])

    def test_resave_with_the_gate_removed_publishes_a_mismatched_section(self):
        # The broken state (origin/main): no identity gate, the section moves
        # to the 13:54 rows while players.json holds 08:48.
        repo, snap, kept = self._repo("nogate")
        self._resave_1354(snap)
        with mock.patch.object(chain, "bake_identity_mismatch", return_value=None), \
                mock.patch.object(chain, "section_identity_mismatch", return_value=None):
            status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=WireFake(repo))
        self.assertNotIn("cbsros", status["held"])
        fixture = json.loads((repo / chain.FIXTURE_REL).read_text())
        self.assertNotEqual(kept, fixture["sources"]["cbsros"])
        self.assertNotEqual(pid.players_ids(repo / chain.PLAYERS_REL)["cbsros"],
                            fixture["sources"]["cbsros"]["snapshot_id"])

    def test_espn_csv_other_than_the_baked_one_holds_espn(self):
        repo, _, _ = self._repo("espn")
        (repo / chain.ESPN_CSV_REL).write_text("player,espn_snapshot_date\nx,2026-10-08\n")
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=WireFake(repo))
        self.assertEqual(["espn"], status["held"])
        self.assertIn("awaiting players bake", status["detail"]["espn"]["detail"])

    def test_section_built_from_another_snapshot_is_held_at_review(self):
        repo, _, kept = self._repo("section")

        class StaleSection(WireFake):
            def __call__(self, cmd, **kw):
                ok, out = super().__call__(cmd, **kw)
                if Path(cmd[1]).name == "build_cbsros_section_from_ddf_leg.py":
                    path = self.repo / chain.FIXTURE_REL
                    doc = json.loads(path.read_text())
                    doc["sources"]["cbsros"]["snapshot_id"] = "sha256:" + "f" * 64
                    path.write_text(json.dumps(doc))
                return ok, out

        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=StaleSection(repo))
        self.assertEqual(["cbsros"], status["held"])
        self.assertEqual("review", status["detail"]["cbsros"]["failed_stage"])
        fixture = json.loads((repo / chain.FIXTURE_REL).read_text())
        self.assertEqual(kept, fixture["sources"]["cbsros"])

    def test_players_json_without_ids_holds_rather_than_guesses(self):
        repo, _, _ = self._repo("legacy")
        players = repo / chain.PLAYERS_REL
        players.write_text(json.dumps({"meta": {"cbsros_snapshot": "2026-10-08"}, "players": []}))
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=WireFake(repo))
        self.assertEqual(["cbsros", "espn", "razzball"], status["held"])


class BakeDecision(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bake-decide-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.csv = self.tmp / "espn.csv"
        self.csv.write_text("player,espn_snapshot_date\nx,2026-10-08\n")
        self.cbs = self.tmp / "cbs.json"
        self.cbs.write_text(json.dumps({"vintage_date": "2026-10-08", "rows": ROWS_0848}))
        self.rz = self.tmp / "rz.json"
        self.rz.write_text(json.dumps({"vintage_date": "2026-10-07", "rows": []}))
        self.players = self.tmp / "players.json"
        self.players.write_text(json.dumps({"meta": {
            "espn_snapshot_id": pid.file_id(self.csv),
            "cbsros_snapshot_id": pid.file_id(self.cbs),
            "rz_snapshot_id": pid.file_id(self.rz)}}))
        self.inputs = {"espn": self.csv, "cbsros": self.cbs, "razzball": self.rz}

    def test_nothing_changed_no_bake(self):
        bake, _ = pid.decide(self.inputs, force=False, players_path=self.players)
        self.assertFalse(bake)

    def test_daily_forced_run_bakes(self):
        bake, _ = pid.decide(self.inputs, force=True, players_path=self.players)
        self.assertTrue(bake)

    def test_cbsros_same_date_resave_bakes(self):
        self.cbs.write_text(json.dumps({"vintage_date": "2026-10-08", "rows": ROWS_1354}))
        bake, lines = pid.decide(self.inputs, force=False, players_path=self.players)
        self.assertTrue(bake)
        self.assertTrue(any(line.startswith("cbsros") and "CHANGED" in line for line in lines))

    def test_espn_and_razzball_changes_bake(self):
        for source, path, text in (("espn", self.csv, "player,espn_snapshot_date\ny,2026-10-08\n"),
                                   ("razzball", self.rz, json.dumps({"vintage_date": "2026-10-08", "rows": []}))):
            with self.subTest(source=source):
                before = path.read_text()
                path.write_text(text)
                self.assertTrue(pid.decide(self.inputs, force=False, players_path=self.players)[0])
                path.write_text(before)

    def test_a_date_only_decision_would_miss_the_incident(self):
        # The broken rule: compare dates. Same date -> "no change" -> no bake.
        self.cbs.write_text(json.dumps({"vintage_date": "2026-10-08", "rows": ROWS_1354}))
        date_rule = json.loads(self.cbs.read_text())["vintage_date"] == "2026-10-08"
        self.assertTrue(date_rule)  # the date rule says "same snapshot"
        self.assertTrue(pid.decide(self.inputs, force=False, players_path=self.players)[0])


class SectionBuildersRefuseMixedLegs(unittest.TestCase):
    def _legs(self, root, ids):
        import build_cbsros_section_from_ddf_leg as sec
        combos = sec.COMBO_KEYS
        for i, combo in enumerate(combos):
            prefix, _, teams = combo.rpartition("_")
            scoring = sec.SCORING_LEG[prefix]
            d = root / f"ddf-20261008-cbsros-{scoring}-{teams}t-0p15"
            d.mkdir(parents=True)
            (d / sec.LEG_FILENAME).write_text(json.dumps({
                "bake_id": d.name, "generated_at": "2026-10-08T14:00:00Z",
                "inputs": {"scoring": scoring, "teams": int(teams),
                           "cbsros_snapshot_date": "2026-10-08",
                           "cbsros_snapshot_id": ids[i % len(ids)]},
                "values": [{"player_key": 869, "player_norm": "josh allen",
                            "ppg": 22.1, "value": 40.0}]}))
        return sec

    def test_one_snapshot_id_is_copied_to_the_section(self):
        with tempfile.TemporaryDirectory() as td:
            sec = self._legs(Path(td), ["sha256:" + "a" * 64])
            with mock.patch.object(sec, "LEG_DIR", Path(td)), \
                    mock.patch.object(sec, "load_slug_to_pos", return_value={}):
                section = sec.section_from_leg({"player_keys": {}}, "u", sec.COMBO_KEYS)
        self.assertEqual("sha256:" + "a" * 64, section["snapshot_id"])

    def test_legs_from_two_snapshots_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            sec = self._legs(Path(td), ["sha256:" + "a" * 64, "sha256:" + "b" * 64])
            with mock.patch.object(sec, "LEG_DIR", Path(td)), \
                    mock.patch.object(sec, "load_slug_to_pos", return_value={}), \
                    self.assertRaises(SystemExit):
                sec.section_from_leg({"player_keys": {}}, "u", sec.COMBO_KEYS)


DATE_KEYS = {  # players.json meta date key, section date field (pre-id fallback)
    "espn": ("espn_snapshot", "espn_snapshot"),
    "cbsros": ("cbsros_snapshot", "vintage"),
    "razzball": ("rz_snapshot", "vintage"),
}


def identity_problems(players_meta, fixture, espn_csv_id=None):
    """Why the browser's projection pricing and the published sections differ."""
    problems = []
    sources = fixture.get("sources") or {}
    for source, (meta_date, section_date) in DATE_KEYS.items():
        section = sources.get(source)
        if not isinstance(section, dict):
            continue
        baked = players_meta.get(pid.META_KEYS[source])
        built = section.get("snapshot_id")
        if baked and built:
            if baked != built:
                problems.append(f"{source}: section snapshot_id {built[:19]} != players.json "
                                f"{pid.META_KEYS[source]} {baked[:19]}")
        elif str(players_meta.get(meta_date)) != str(section.get(section_date)):
            problems.append(f"{source}: section {section_date} {section.get(section_date)!r} != "
                            f"players.json {meta_date} {players_meta.get(meta_date)!r}")
    baked_espn = players_meta.get("espn_snapshot_id")
    if baked_espn and espn_csv_id and baked_espn != espn_csv_id:
        problems.append(f"players.json espn_snapshot_id {baked_espn[:19]} is not the committed "
                        f"ESPN CSV {espn_csv_id[:19]}")
    return problems


class PublishedProjectionsAreOneSnapshot(unittest.TestCase):
    def test_committed_fixture(self):
        meta = json.loads(PLAYERS.read_text())["meta"]
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual([], identity_problems(meta, fixture, pid.file_id(ESPN_CSV)))

    def test_guard_catches_the_incident_state(self):
        # 2026-10-08 13:57: same date on both sides, different content ids.
        meta = {"cbsros_snapshot": "2026-10-08", "cbsros_snapshot_id": "sha256:" + "a" * 64}
        fixture = {"sources": {"cbsros": {"vintage": "2026-10-08",
                                          "snapshot_id": "sha256:" + "b" * 64}}}
        self.assertEqual(1, len(identity_problems(meta, fixture)))
        fixture["sources"]["cbsros"]["snapshot_id"] = "sha256:" + "a" * 64
        self.assertEqual([], identity_problems(meta, fixture))

    def test_guard_falls_back_to_dates_before_ids_exist(self):
        meta = {"rz_snapshot": "2026-09-22"}
        fixture = {"sources": {"razzball": {"vintage": "2026-10-01"}}}
        self.assertEqual(1, len(identity_problems(meta, fixture)))

    def test_guard_catches_a_csv_other_than_the_baked_one(self):
        meta = {"espn_snapshot_id": "sha256:" + "a" * 64}
        self.assertEqual(1, len(identity_problems(meta, {}, "sha256:" + "c" * 64)))


def _step(text, name):
    """The body of the workflow step named `name` (up to the next step)."""
    start = text.index(f"- name: {name}")
    nxt = text.find("\n      - name: ", start + 1)
    return text[start: nxt if nxt != -1 else len(text)]


class ManualBakeUsesTheChainInputs(unittest.TestCase):
    """7. bake-players.yml (manual) bakes CBS ROS / Razzball from the same
    files as the chain's bake: the importer's snapshots, picked by
    projection_identity decide. A re-export (export_cbsros_snapshot.py) is
    another file with another cbsros_snapshot_id, so the next chain run held
    CBS ROS and re-baked."""

    def setUp(self):
        self.text = (ROOT / ".github/workflows/bake-players.yml").read_text(encoding="utf-8")

    def test_no_second_cbsros_export(self):
        self.assertNotIn("export_cbsros_snapshot", self.text)

    def test_imports_then_decides_then_bakes_the_decided_files(self):
        imp = _step(self.text, "Import CBS ROS and Razzball snapshots from Supabase")
        self.assertIn("import_supabase_references.py --source cbsros", imp)
        self.assertIn("import_supabase_references.py --source razzball", imp)
        self.assertIn("projection_identity.py decide --force true", imp)
        self.assertLess(imp.index("--source cbsros"), imp.index("decide"))
        bake = _step(self.text, "Bake players.json")
        self.assertIn("CBSROS_SNAPSHOT: ${{ steps.inputs.outputs.cbsros_snapshot }}", bake)
        self.assertIn("RAZZBALL_SNAPSHOT: ${{ steps.inputs.outputs.razzball_snapshot }}", bake)
        self.assertIn('--cbsros-snapshot "$CBSROS_SNAPSHOT"', bake)
        self.assertIn('--razzball-snapshot "$RAZZBALL_SNAPSHOT"', bake)

    def test_the_chain_bakes_the_same_way(self):
        chain_text = (ROOT / ".github/workflows/rebuild-chain.yml").read_text(encoding="utf-8")
        self.assertIn("import_supabase_references.py --source", chain_text)
        self.assertIn("projection_identity.py decide", chain_text)
        self.assertIn('--cbsros-snapshot "$CBSROS_SNAPSHOT"', chain_text)

    def test_decide_outputs_the_imported_snapshot(self):
        # decide's default CBS ROS input is the chain's own latest snapshot
        # lookup over data/raw/sources (where the importer writes).
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            for day in ("2026-10-07", "2026-10-08"):
                d = repo / "data" / "raw" / "sources" / "cbsros" / day
                d.mkdir(parents=True)
                (d / "snapshot.json").write_text(json.dumps({"vintage_date": day, "rows": []}))
            got = pid.latest_snapshot("cbsros", repo)
        self.assertEqual(("2026-10-08", "snapshot.json"), (got.parent.name, got.name))


if __name__ == "__main__":
    unittest.main()
