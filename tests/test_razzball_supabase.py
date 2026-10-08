"""Razzball through Supabase (JEG-18): saver, importer and the round trip.

Razzball used to be file-only. These tests pin the contract that mirrors cbsros:
  - the saver stores the published per-game columns and keeps every other row field
    in raw_stats, stamped from the snapshot vintage;
  - the importer rebuilds the NATIVE snapshot the DDF leg reads, from table rows;
  - a file-built snapshot and a DB-rebuilt snapshot carry the same values, and the
    real leg builder (build_razzball_ddf_leg.load_razzball_lists) reads the rebuilt
    one and prices the same numbers;
  - ecr/vegas/prediction markets stay hard-excluded.
No network: Supabase access is injected through the modules' callables. The real
snapshot only exists on the owner's machine, so rows here are synthetic, shaped
from data/inputs/razzball_projections.csv and what the leg builder reads.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"
sys.path.insert(0, str(PIPELINES))
sys.path.insert(0, str(PIPELINES / "lib"))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PIPELINES / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


importer = load("import_supabase_references", "import_supabase_references.py")
saver = load("save_razzball_references", "save_razzball_references.py")
leg = load("build_razzball_ddf_leg", "build_razzball_ddf_leg.py")

PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB"},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB"},
]


def snapshot_row(name, norm, pos, team, std, half, ppr, **extra):
    row = {
        "player_name": name, "player_norm": norm, "pos": pos, "team": team,
        "health": "", "games_reported": 32.0,
        "pg_pass_yds": 240.0, "pg_rush_att": 6.975, "share_rush": 0.0,
        "rz_std_ppg": std, "rz_half_ppr_ppg": half, "rz_ppr_ppg": ppr,
    }
    row.update(extra)
    return row


SNAPSHOT_ROWS = [
    snapshot_row("Josh Allen", "josh allen", "QB", "BUF", 21.6, 21.6, 21.6),
    snapshot_row("Jahmyr Gibbs", "jahmyr gibbs", "RB", "DET", 17.0, 19.5, 22.0,
                 pg_rush_att=15.2, share_rush=0.62),
]


def write_snapshot(directory, vintage="2026-10-01", rows=None):
    path = Path(directory) / f"snap_{vintage}" / "snapshot.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema": "trade-value-razzball-snapshot-v1", "vintage_date": vintage,
        "rows": SNAPSHOT_ROWS if rows is None else rows,
    }), encoding="utf-8")
    return path


class MigrationMatchesSaverTest(unittest.TestCase):
    """The saver can only write columns the table has; a missing column is a 400 at
    the first real save, after the table was already created. Guard it here."""

    SQL = (ROOT / "sql" / "migrations" / "003_razzball_projections.sql").read_text()

    def columns(self):
        import re
        body = self.SQL.split("CREATE TABLE IF NOT EXISTS public.razzball_projections (", 1)[1]
        body = body.split("\n);", 1)[0]
        cols = set()
        for line in body.splitlines():
            line = line.split("--", 1)[0].strip()
            m = re.match(r"([a-z_]+)\s+[A-Z]", line)
            if m:
                cols.add(m.group(1))
        return cols

    def test_every_column_the_saver_writes_exists_in_the_migration(self):
        saver.fetch_players = lambda: PLAYERS
        try:
            with tempfile.TemporaryDirectory() as tmp:
                clean, _, _ = saver.build_razzball_rows(write_snapshot(tmp))
        finally:
            saver.fetch_players = saver._default_fetch_players
        written = set().union(*(row.keys() for row in clean))
        self.assertEqual(set(), written - self.columns(), "saver writes columns the table lacks")

    def test_every_column_the_importer_reads_exists_in_the_migration(self):
        for col in ("player_key", "player_norm", "pos", "team", "health", "games_reported",
                    "per_game_standard", "per_game_half_ppr", "per_game_ppr", "raw_stats",
                    "razzball_snapshot_date", "week"):
            self.assertIn(col, self.columns())

    def test_upsert_key_is_a_unique_index_matching_the_saver(self):
        self.assertEqual("player_key,razzball_snapshot_date", saver.CONFLICT)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS razzball_projections_player_date_uidx", self.SQL)
        self.assertIn("(player_key, razzball_snapshot_date)", self.SQL)

    def test_the_migration_creates_only_this_table_and_the_rollback_stays_a_comment(self):
        self.assertEqual(1, self.SQL.count("CREATE TABLE"))
        executable = [l.strip() for l in self.SQL.splitlines()
                      if l.strip() and not l.strip().startswith("--")]
        for line in executable:
            self.assertFalse(line.upper().startswith(("DROP ", "DELETE ", "TRUNCATE ", "ALTER ")),
                             f"destructive statement is executable: {line}")
        self.assertIn("-- Rollback", self.SQL)
        self.assertIn("DROP TABLE IF EXISTS public.razzball_projections;", self.SQL)


class IdentityResolutionTest(unittest.TestCase):
    """The first dry run against the real 2026-10-01 snapshot dropped 21 of 701 players,
    including Ja'Marr Chase, because public.players uses straight apostrophes and the
    snapshot uses typographic ones. These pin the fixes and keep the fail-closed rules."""

    PLAYERS = [
        {"player_key": 1, "full_name": "Ja'Marr Chase", "position": "WR"},
        {"player_key": 2, "full_name": "David Sills", "position": "WR"},
        {"player_key": 3, "full_name": "Josh Sills", "position": "OL"},
        {"player_key": 4, "full_name": "Audric Estim\u00e9", "position": "RB"},
        {"player_key": 5, "full_name": "Audric Estime", "position": "RB"},
        {"player_key": 6, "full_name": "Pat Twin", "position": "WR"},
        {"player_key": 7, "full_name": "Pat Twin", "position": "TE"},
        {"player_key": 8, "full_name": "Josh Palmer", "position": "WR"},
    ]

    def resolve(self, name, pos, hint=None):
        index = saver.build_name_index(self.PLAYERS)
        return saver.resolve_name(name, pos, index, hint)

    def test_typographic_apostrophe_matches_the_straight_apostrophe_name(self):
        self.assertEqual((1, None), self.resolve("Ja\u2019Marr Chase", "WR"))
        self.assertEqual((1, None), self.resolve("Ja'Marr Chase", "WR"))

    def test_the_snapshots_own_player_norm_resolves_a_suffix_spelling(self):
        self.assertEqual((None, "no_match"), self.resolve("David Sills V", "WR"))
        self.assertEqual((2, None), self.resolve("David Sills V", "WR", "david sills"))

    def test_the_hint_never_overrides_a_name_that_already_resolves(self):
        self.assertEqual((2, None), self.resolve("David Sills", "WR", "josh sills"))

    def test_duplicate_players_stay_ambiguous_and_are_never_guessed(self):
        self.assertEqual((None, "ambiguous"), self.resolve("Audric Estime", "RB"))

    def test_position_narrows_same_named_players(self):
        self.assertEqual((6, None), self.resolve("Pat Twin", "WR"))
        self.assertEqual((7, None), self.resolve("Pat Twin", "TE"))

    def test_nicknames_are_not_guessed(self):
        # A long-form first name needs a verified alias, not a heuristic.
        # (This used "Joshua Palmer" until 2026-10-08, when that spelling got
        # a verified alias in build_ddf_two_tier_leg.ALIASES; see below.)
        self.assertEqual((None, "no_match"), self.resolve("Patrick Twin", "WR", "patrick twin"))
        self.assertEqual((None, "no_match"), self.resolve("Nobody Real", "WR", "nobody real"))

    def test_verified_nickname_aliases_resolve(self):
        # GAP-RAZZBALL-SUFFIX-POOL: Razzball's 2026-10-06 save sent these to
        # review; each alias target is the single public.players row.
        players = self.PLAYERS + [
            {"player_key": 920, "full_name": "Andrew Ogletree", "position": "TE"},
            {"player_key": 4247, "full_name": "Chig Okonkwo", "position": "TE"},
            {"player_key": 4214, "full_name": "Mitchell Trubisky", "position": "QB"},
            {"player_key": 785, "full_name": "Kenneth Gainwell", "position": "RB"},
        ]
        index = saver.build_name_index(players)
        for name, pos, key in (("Joshua Palmer", "WR", 8), ("Drew Ogletree", "TE", 920),
                               ("Chigoziem Okonkwo", "TE", 4247),
                               ("Mitch Trubisky", "QB", 4214), ("Kenny Gainwell", "RB", 785)):
            self.assertEqual((key, None), saver.resolve_name(name, pos, index, name.lower()), name)


class SaverTest(unittest.TestCase):
    def setUp(self):
        self._fetch = saver.fetch_players
        saver.fetch_players = lambda: PLAYERS
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, saver, "fetch_players", self._fetch)

    def test_rows_carry_per_game_values_and_keep_the_rest_in_raw_stats(self):
        clean, review, vintage = saver.build_razzball_rows(write_snapshot(self.tmp.name))
        self.assertEqual("2026-10-01", vintage)
        self.assertEqual([], review)
        gibbs = next(r for r in clean if r["player_key"] == 2227)
        self.assertEqual(17.0, gibbs["per_game_standard"])
        self.assertEqual(19.5, gibbs["per_game_half_ppr"])
        self.assertEqual(22.0, gibbs["per_game_ppr"])
        self.assertEqual({"pg_pass_yds": 240.0, "pg_rush_att": 15.2, "share_rush": 0.62},
                         gibbs["raw_stats"])
        self.assertEqual("DET", gibbs["team"])
        self.assertEqual("razzball-save-2026-10-01", gibbs["_run_id"])

    def test_stamps_come_from_the_vintage_not_the_run_date(self):
        clean, _, _ = saver.build_razzball_rows(write_snapshot(self.tmp.name, "2026-09-16"))
        self.assertEqual("2026-09-16", clean[0]["razzball_snapshot_date"])
        self.assertEqual("2026-09-16", clean[0]["source_content_date"])
        self.assertEqual(2026, clean[0]["season"])
        self.assertEqual(2, clean[0]["week"])
        # Far from today's date, so a run-date stamp cannot pass by coincidence.
        for vintage, season in (("2029-01-15", 2028), ("2029-09-10", 2029), ("2027-02-01", 2026)):
            clean, _, _ = saver.build_razzball_rows(write_snapshot(self.tmp.name, vintage))
            self.assertEqual(season, clean[0]["season"], vintage)  # Jan-Jul = prior season

    def test_unmatched_and_ambiguous_names_go_to_review_never_guessed(self):
        rows = SNAPSHOT_ROWS + [snapshot_row("Nobody Real", "nobody real", "WR", "X", 1, 1, 1)]
        clean, review, _ = saver.build_razzball_rows(write_snapshot(self.tmp.name, rows=rows))
        self.assertEqual(2, len(clean))
        self.assertEqual(["no_match"], [r["reason"] for r in review])

    def test_fail_closed_on_bad_snapshots(self):
        for vintage, rows in ((None, SNAPSHOT_ROWS), ("not-a-date", SNAPSHOT_ROWS),
                              ("2026-10-01", [])):
            path = Path(self.tmp.name) / f"bad_{vintage}" / "snapshot.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            doc = {"rows": rows}
            if vintage:
                doc["vintage_date"] = vintage
            path.write_text(json.dumps(doc), encoding="utf-8")
            with self.assertRaises(SystemExit, msg=str(vintage)):
                saver.build_razzball_rows(path)

    def test_main_fails_closed_when_the_table_count_disagrees_after_upsert(self):
        written = []
        saved = (saver.upsert_rows, saver.count_rows)
        saver.upsert_rows = lambda table, rows, conflict: written.append((table, len(rows), conflict))
        saver.count_rows = lambda table, params: 1  # table holds fewer rows than upserted
        argv = sys.argv
        sys.argv = ["save", "--snapshot", str(write_snapshot(self.tmp.name))]
        try:
            with self.assertRaises(SystemExit) as ctx:
                saver.main()
        finally:
            sys.argv = argv
            saver.upsert_rows, saver.count_rows = saved
        self.assertIn("expected 2", str(ctx.exception))
        self.assertEqual([("razzball_projections", 2, "player_key,razzball_snapshot_date")], written)


class ImporterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outdir = Path(self.tmp.name) / "sources"
        self.addCleanup(self.tmp.cleanup)
        saved = (importer.fetch_supabase_rows, importer.fetch_player_names,
                 importer.fetch_player_positions, importer.fixture_pos_team)
        importer.fetch_player_names = lambda keys: {869: "Josh Allen", 2227: "Jahmyr Gibbs"}
        importer.fetch_player_positions = lambda keys: {869: "QB", 2227: "RB"}
        importer.fixture_pos_team = lambda: {869: ("QB", "BUF"), 2227: ("RB", "DET")}
        self.addCleanup(lambda: (setattr(importer, "fetch_supabase_rows", saved[0]),
                                 setattr(importer, "fetch_player_names", saved[1]),
                                 setattr(importer, "fetch_player_positions", saved[2]),
                                 setattr(importer, "fixture_pos_team", saved[3])))

    def import_rows(self, rows):
        importer.fetch_supabase_rows = lambda table, params: rows
        return importer.import_source("razzball", output_dir=self.outdir)

    def table_rows(self, vintage="2026-10-01"):
        saver.fetch_players = lambda: PLAYERS
        try:
            clean, _, _ = saver.build_razzball_rows(write_snapshot(self.tmp.name, vintage))
        finally:
            saver.fetch_players = saver._default_fetch_players
        return clean

    def test_razzball_is_importable_and_the_real_exclusions_remain(self):
        self.assertIn("razzball", importer.DASHBOARD_SOURCES)
        self.assertEqual("razzball", importer.check_source("razzball"))
        for bad in ("ecr", "vegas", "prediction_markets", "fantasypros_ecr"):
            with self.assertRaises(SystemExit, msg=bad):
                importer.check_source(bad)

    def test_zero_rows_fails_closed_and_writes_nothing(self):
        with self.assertRaises(SystemExit):
            self.import_rows([])
        self.assertEqual([], list(self.outdir.rglob("snapshot.json")))

    def test_native_shape_and_manifest(self):
        result = self.import_rows(self.table_rows())
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual("trade-value-razzball-snapshot-v1", snapshot["schema"])
        self.assertEqual("2026-10-01", snapshot["vintage_date"])  # the leg fail-closes without it
        self.assertEqual("2026-10-01", result["content_vintage"])
        self.assertEqual(2, snapshot["row_count"])
        manifest = json.loads(result["manifest_path"].read_text())
        self.assertEqual("public.razzball_projections", manifest["supabase_table"])
        self.assertIsNone(manifest["week_designated"])  # daily rule, never a week label
        self.assertIn("razzball_snapshot_date", manifest["content_vintage_derived_from"])

    def test_the_tables_razzball_position_wins_over_the_canonical_one(self):
        # public.players says RB; Razzball (and so the leg) said TE. The rebuilt row
        # must keep Razzball's label so the two build paths bucket the player the same.
        importer.fetch_player_positions = lambda keys: {869: "RB", 2227: "RB"}
        rows = self.table_rows()
        snapshot = json.loads(self.import_rows(rows)["snapshot_path"].read_text())
        by_name = {r["player_name"]: r["pos"] for r in snapshot["rows"]}
        self.assertEqual("QB", by_name["Josh Allen"])  # the table's pos, not players.position

    def test_missing_per_game_goes_to_review(self):
        rows = self.table_rows()
        rows[0]["per_game_ppr"] = None
        snapshot = json.loads(self.import_rows(rows)["snapshot_path"].read_text())
        self.assertEqual(1, snapshot["row_count"])
        self.assertEqual("missing_or_non_numeric_per_game", snapshot["review_rows"][0]["reason"])

    def test_latest_snapshot_date_wins_and_vintages_never_blend(self):
        old = [dict(r, razzball_snapshot_date="2026-09-22", source_content_date="2026-09-22")
               for r in self.table_rows()]
        new = self.table_rows("2026-10-01")
        snapshot = json.loads(self.import_rows(old + new)["snapshot_path"].read_text())
        self.assertEqual("2026-10-01", snapshot["vintage_date"])
        self.assertEqual(2, snapshot["row_count"])

    def test_round_trip_file_to_table_to_snapshot_carries_the_same_values(self):
        original = {r["player_name"]: r for r in SNAPSHOT_ROWS}
        snapshot = json.loads(self.import_rows(self.table_rows())["snapshot_path"].read_text())
        rebuilt = {r["player_name"]: r for r in snapshot["rows"]}
        self.assertEqual(set(original), set(rebuilt))
        for name, row in original.items():
            # The DB-rebuilt row also carries the saver's verified player_key
            # (bake_players.py prices the browser's rz_ppg by it); every
            # file field survives unchanged.
            got = dict(rebuilt[name])
            self.assertEqual({"Josh Allen": 869, "Jahmyr Gibbs": 2227}[name], got.pop("player_key"), name)
            self.assertEqual(row, got, name)

    def test_the_real_leg_builder_reads_the_rebuilt_snapshot_and_gets_the_same_numbers(self):
        result = self.import_rows(self.table_rows())
        fixture = Path(self.tmp.name) / "fixture.json"
        fixture.write_text(json.dumps({"player_keys": {"josh allen": 869, "jahmyr gibbs": 2227}}))
        resolved, review, _, meta = leg.load_razzball_lists(result["snapshot_path"], "half_ppr", fixture)
        self.assertEqual([], review)
        self.assertEqual("2026-10-01", meta["razzball_vintage_date"])
        self.assertEqual(21.6, resolved["QB"][0]["x"])
        self.assertEqual(19.5, resolved["RB"][0]["x"])  # rz_half_ppr_ppg survived the round trip


if __name__ == "__main__":
    unittest.main()
