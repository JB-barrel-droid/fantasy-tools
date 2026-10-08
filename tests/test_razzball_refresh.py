"""GAP-RAZZBALL-SUFFIX-POOL / GAP-RAZZBALL-STALE-BAKE (2026-10-08).

Two defects kept the published Razzball numbers on old data:

1. The comparison chain imported public.razzball_projections on every run but
   never rebuilt the Razzball legs or section (rebuild_comparison_chain.SOURCES
   omitted razzball), so the section stayed on its last hand build (2026-10-01,
   built before the suffix fix, missing 27 players).
2. The browser prices Razzball from players.json rz_ppg, which bake_players.py
   read from data/inputs/razzball_projections.csv -- a 2026-09-22 file nothing
   refreshed. The freshness label reads the section's vintage (2026-10-01), so
   the page labelled Week 3 numbers as Week 4.

Every guard below is negative-tested against the broken state it names.
"""
import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "tests"))

import rebuild_comparison_chain as chain  # noqa: E402
import bake_players  # noqa: E402
from test_rebuild_chain_failclosed import WireFake as _WireFake, make_repo, simulate_bake  # noqa: E402
import projection_identity  # noqa: E402


class WireFake(_WireFake):
    """The parent's cbsros/espn section fakes rewrite the whole fixture; keep
    the other sources (here: a seeded razzball section) like the real
    builders do."""

    def __call__(self, cmd, **kwargs):
        path = self.repo / chain.FIXTURE_REL
        before = json.loads(path.read_text()) if path.is_file() else {}
        ok, out = super().__call__(cmd, **kwargs)
        if Path(cmd[1]).name in ("build_cbsros_section_from_ddf_leg.py",
                                 "build_espn_section_from_ddf_leg.py") and path.is_file():
            after = json.loads(path.read_text())
            merged = dict(before)
            merged["sources"] = {**(before.get("sources") or {}), **after["sources"]}
            path.write_text(json.dumps(merged))
        return ok, out

FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"
HARNESS = ROOT / "tests" / "cbsros_live_section_harness.js"


def vintage_problems(players_meta, fixture):
    """Why the browser's Razzball and the Razzball section disagree, or []."""
    section = (fixture.get("sources") or {}).get("razzball") or {}
    baked = (players_meta or {}).get("rz_snapshot")
    if not section:
        return []
    if baked != section.get("vintage"):
        return [f"players.json rz_snapshot {baked!r} != razzball section vintage "
                f"{section.get('vintage')!r}: the browser prices one Razzball "
                "vintage while the label and main table show another"]
    return []


class VintageParityGuard(unittest.TestCase):
    """The live (players.json) Razzball and the section are one vintage."""

    def test_published_razzball_is_one_vintage(self):
        meta = json.loads(PLAYERS.read_text())["meta"]
        fixture = json.loads(FIXTURE.read_text())
        self.assertEqual([], vintage_problems(meta, fixture))

    def test_guard_catches_the_origin_main_state(self):
        # origin/main 196906f: players.json rz_snapshot 2026-09-22, section 2026-10-01.
        broken = vintage_problems({"rz_snapshot": "2026-09-22"},
                                  {"sources": {"razzball": {"vintage": "2026-10-01"}}})
        self.assertEqual(1, len(broken))
        self.assertEqual([], vintage_problems({"rz_snapshot": "2026-10-06"},
                                              {"sources": {"razzball": {"vintage": "2026-10-06"}}}))


class LiveSectionParity(unittest.TestCase):
    """Browser-side Razzball repricing == the published section (<= 0.2).

    origin/main: max |live - section| 31.4 (live pool 511 players from the
    2026-09-22 CSV, section 469 from 2026-10-01).
    """

    def test_live_razzball_matches_section(self):
        out = subprocess.run(["node", str(HARNESS), "browser-pool", "razzball"],
                             capture_output=True, text=True, check=True, cwd=ROOT)
        data = json.loads(out.stdout)
        self.assertEqual(12, len(data))
        worst = max((s["maxErr"], combo, pos) for combo, v in data.items()
                    for pos, s in v["stats"].items())
        self.assertLess(worst[0], 0.2, worst)
        for combo, v in data.items():
            self.assertEqual([], v["withheld"], combo)
            for pos, s in v["stats"].items():
                # Every section player is priced live (the browser can only
                # carry extra players with no fixture slug).
                self.assertEqual(s["n"], s["nSection"], (combo, pos))
                self.assertGreater(s["n"], 0, (combo, pos))


class ChainRebuildsRazzball(unittest.TestCase):
    """rebuild_comparison_chain runs snapshot -> 12 legs -> section for razzball."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_razzball_is_a_chain_source(self):
        self.assertIn("razzball", chain.SOURCES)

    def test_chain_rebuilds_the_razzball_section(self):
        repo = make_repo(Path(self.tmp.name) / "ok", tuple(chain.SOURCES))
        fake = WireFake(repo)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=fake)
        self.assertEqual(12, fake.calls.count("build_razzball_ddf_leg.py"))
        self.assertIn("build_razzball_section_from_ddf_leg.py", fake.calls)
        self.assertEqual("ok", status["detail"]["razzball"]["status"])
        self.assertEqual([], status["held"])
        fixture = json.loads((repo / chain.FIXTURE_REL).read_text())
        self.assertEqual(12, len(fixture["sources"]["razzball"]["combos"]))

    def _held_run(self, tag, mutate):
        repo = make_repo(Path(self.tmp.name) / tag, tuple(chain.SOURCES))
        fpath = repo / chain.FIXTURE_REL
        fpath.parent.mkdir(parents=True, exist_ok=True)
        kept = {"vintage": "2026-09-22", "combos": {"full_12": {"values": {"x": 1.0}}}}
        fpath.write_text(json.dumps({"sources": {"razzball": kept}}))
        mutate(repo)
        fake = WireFake(repo)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=fake)
        fixture = json.loads(fpath.read_text())
        return status, fixture, fake, kept

    def test_unbaked_vintage_holds_razzball_and_keeps_its_section(self):
        def newer_than_bake(repo):
            # players.json baked from another Razzball snapshot (GAP-BAKE-ON-
            # CHANGE: identity is the content id, so even a same-date resave
            # with other numbers holds the section).
            simulate_bake(repo, razzball="sha256:" + "0" * 64)
        status, fixture, fake, kept = self._held_run("unbaked", newer_than_bake)
        self.assertEqual(["razzball"], status["held"])
        self.assertTrue(status["success"], status["failed"])
        self.assertIn("awaiting players bake", status["detail"]["razzball"]["detail"])
        self.assertNotIn("build_razzball_ddf_leg.py", fake.calls)
        self.assertEqual(kept, fixture["sources"]["razzball"])

    def test_a_razzball_leg_failure_is_isolated(self):
        repo = make_repo(Path(self.tmp.name) / "legfail", tuple(chain.SOURCES))
        fpath = repo / chain.FIXTURE_REL
        kept = {"vintage": "2026-09-22", "combos": {}}
        fpath.write_text(json.dumps({"sources": {"razzball": kept}}))
        fake = WireFake(repo)

        def failing(cmd, **kw):
            if Path(cmd[1]).name == "build_razzball_ddf_leg.py":
                return False, "boom"
            return fake(cmd, **kw)
        status = chain.execute_chain(nfl_week=5, repo=repo, run_fn=failing)
        self.assertEqual(["razzball"], status["held"])
        self.assertTrue(status["success"], status["failed"])
        self.assertEqual(kept, json.loads(fpath.read_text())["sources"]["razzball"])

    def test_bake_gate_reasons(self):
        # Since GAP-BAKE-ON-CHANGE (2026-10-08) the gate compares the
        # snapshot's content id with players.json rz_snapshot_id; the old
        # date compare passed two same-date snapshots with different numbers.
        repo = Path(self.tmp.name) / "gate"
        snap = repo / "snap.json"
        snap.parent.mkdir(parents=True)
        rows = [{"player_key": 1, "rz_ppr_ppg": 10.0}, {"player_key": 2, "rz_ppr_ppg": 9.0}]
        snap.write_text(json.dumps({"vintage_date": "2026-10-06", "rows": rows}))
        sid = projection_identity.file_id(snap)
        players = repo / chain.PLAYERS_REL
        players.parent.mkdir(parents=True)
        players.write_text(json.dumps({"meta": {"rz_snapshot": "2026-10-06",
                                                "rz_snapshot_id": sid}}))
        self.assertIsNone(chain.razzball_bake_mismatch(repo, snap))
        # Same date, one changed value: the date gate passed this.
        snap.write_text(json.dumps({"vintage_date": "2026-10-06",
                                    "rows": [{"player_key": 1, "rz_ppr_ppg": 11.0}, rows[1]]}))
        self.assertIn("awaiting players bake", chain.razzball_bake_mismatch(repo, snap))
        # Row order alone is not a different snapshot.
        snap.write_text(json.dumps({"vintage_date": "2026-10-06", "rows": rows[::-1]}))
        self.assertIsNone(chain.razzball_bake_mismatch(repo, snap))
        players.write_text(json.dumps({"meta": {"rz_snapshot": "2026-10-06"}}))
        self.assertIn("no rz_snapshot_id", chain.razzball_bake_mismatch(repo, snap))
        players.unlink()
        self.assertIn("players.json", chain.razzball_bake_mismatch(repo, snap))


class BakeReadsTheSupabaseSnapshot(unittest.TestCase):
    """bake_players.py prices rz_ppg from the imported snapshot, by player_key."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _snapshot(self, rows, vintage="2026-10-06"):
        path = Path(self.tmp.name) / vintage / "snapshot.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"vintage_date": vintage, "rows": rows}))
        return path

    def test_snapshot_intake_uses_the_saved_key_and_vintage(self):
        path = self._snapshot([
            {"player_key": 1095, "player_name": "Kenneth Walker III", "pos": "RB",
             "rz_std_ppg": 19.4, "rz_half_ppr_ppg": 20.9, "rz_ppr_ppg": 22.4},
            {"player_key": 869, "player_name": "Josh Allen", "pos": "QB",
             "rz_std_ppg": 21.5, "rz_half_ppr_ppg": 21.5, "rz_ppr_ppg": None},
        ])
        with mock.patch.object(bake_players, "_resolve_csv_row",
                               side_effect=AssertionError("must not re-resolve a keyed row")):
            med, vintage = bake_players._intake_razzball_snapshot(path, registry=None)
        self.assertEqual("2026-10-06", vintage)
        self.assertEqual({1095: {"standard": 19.4, "half_ppr": 20.9, "ppr": 22.4}}, med)

    def test_snapshot_without_vintage_fails_closed(self):
        path = Path(self.tmp.name) / "bad.json"
        path.write_text(json.dumps({"rows": []}))
        with self.assertRaises(SystemExit):
            bake_players._intake_razzball_snapshot(path, registry=None)

    def test_cli_defaults_to_the_latest_imported_snapshot(self):
        root = Path(self.tmp.name) / "raw"
        for v in ("2026-10-01", "2026-10-06"):
            p = root / v / "snapshot.json"
            p.parent.mkdir(parents=True)
            p.write_text(json.dumps({"vintage_date": v, "rows": []}))
        with mock.patch.object(bake_players, "RAZZBALL_SNAPSHOT_DIR", root):
            self.assertEqual(root / "2026-10-06" / "snapshot.json",
                             bake_players._latest_razzball_snapshot())

    def test_bake_uses_the_snapshot_not_the_csv(self):
        # origin/main read data/inputs/razzball_projections.csv unconditionally.
        path = self._snapshot([{"player_key": 1095, "player_name": "x", "pos": "RB",
                                "rz_std_ppg": 1.0, "rz_half_ppr_ppg": 2.0, "rz_ppr_ppg": 3.0}])
        args = argparse.Namespace(razzball_snapshot=str(path), razzball_csv="/nonexistent.csv")
        with mock.patch.object(bake_players, "_intake_razzball",
                               side_effect=AssertionError("read the stale CSV")):
            med, vintage = bake_players.razzball_intake(args, registry=None)
        self.assertEqual(("2026-10-06", [1095]), (vintage, list(med)))

    def test_rebuild_chain_bake_passes_the_razzball_snapshot(self):
        text = (ROOT / ".github/workflows/rebuild-chain.yml").read_text()
        self.assertIn("--razzball-snapshot", text)
        text = (ROOT / ".github/workflows/bake-players.yml").read_text()
        self.assertIn("--razzball-snapshot", text)
        self.assertIn("import_supabase_references.py --source razzball", text)


if __name__ == "__main__":
    unittest.main()
