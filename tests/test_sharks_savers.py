"""JEG-620 / JEG-621: Draft Sharks and Fantasy Sharks savers and migrations. Hermetic.

Pins: the saver writes only columns its migration creates; the upsert key is a
unique index; the migrations only create (no drop/alter/delete) and enable RLS;
nulls stay null (never zero); stamps come from the snapshot vintage; unmatched
names go to review, never guessed; an empty or undated snapshot fails closed.
"""
import contextlib
import io
import json
import re
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import save_draftsharks_references as ds  # noqa: E402
import save_fantasysharks_references as fs  # noqa: E402

PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB", "active": True},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB", "active": True},
]
DS_ROWS = [
    {"player_name": "Josh Allen", "player_norm": "josh allen", "pos": "QB", "team": "BUF", "draftsharks_id": 11,
     "ds": {"redraft_no_ppr": 80.0, "redraft_half_ppr": 81.0, "redraft_one_ppr": None, "dynasty_half_ppr": 70.0},
     "market": {"redraft_half_ppr": 79.0}},
    {"player_name": "Nobody Real", "player_norm": "nobody real", "pos": "WR", "team": "X", "draftsharks_id": 12,
     "ds": {"redraft_half_ppr": 5.0}, "market": {}},
]
FS_ROWS = [
    {"player_name": "Jahmyr Gibbs", "player_norm": "jahmyr gibbs", "pos": "RB", "team": "DET", "fantasysharks_id": 21,
     "pts": {"non_ppr": 150.5, "half_ppr": 170.0, "ppr": None}},
]


def snapshot(tmp, rows, vintage="2026-10-15"):
    p = Path(tmp) / vintage / "snapshot.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"vintage_date": vintage, "rows": rows}), encoding="utf-8")
    return p


def table_columns(sql, table):
    body = sql.split(f"CREATE TABLE IF NOT EXISTS public.{table} (", 1)[1].split("\n);", 1)[0]
    cols = set()
    for line in body.splitlines():
        m = re.match(r"([a-z_]+)\s+[A-Z]", line.split("--", 1)[0].strip())
        if m:
            cols.add(m.group(1))
    return cols


CASES = ((ds, DS_ROWS, "008_draftsharks_trade_values.sql", "draftsharks_trade_values"),
         (fs, FS_ROWS, "009_fantasysharks_projections.sql", "fantasysharks_projections"))


class SharksSaverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for mod, *_ in CASES:
            self.addCleanup(setattr, mod, "fetch_players", mod.fetch_players)
            mod.fetch_players = lambda: PLAYERS

    def test_saver_writes_only_migration_columns_and_the_key_is_unique(self):
        for mod, rows, mig, table in CASES:
            sql = (ROOT / "sql" / "migrations" / mig).read_text(encoding="utf-8")
            clean, _, _ = mod.build_rows(snapshot(self.tmp.name, rows))
            written = set().union(*(r.keys() for r in clean))
            self.assertEqual(set(), written - table_columns(sql, table), mod.SOURCE)
            self.assertEqual(table, mod.TABLE)
            self.assertIn(f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_player_date_uidx", sql)
            self.assertEqual(f"player_key,{mod.SNAPSHOT_COLUMN}", mod.CONFLICT)

    def test_migrations_only_create_and_enable_rls(self):
        for _, _, mig, table in CASES:
            sql = (ROOT / "sql" / "migrations" / mig).read_text(encoding="utf-8")
            lines = [l.strip() for l in sql.splitlines() if l.strip() and not l.strip().startswith("--")]
            self.assertEqual(1, sum(l.startswith("CREATE TABLE") for l in lines))
            for line in lines:
                if line.upper().startswith("ALTER TABLE"):
                    self.assertEqual(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;", line)
                self.assertFalse(line.upper().startswith(("DROP ", "DELETE ", "TRUNCATE ")), line)

    def test_nulls_stay_null_and_unmatched_goes_to_review(self):
        clean, review, vintage = ds.build_rows(snapshot(self.tmp.name, DS_ROWS))
        self.assertEqual("2026-10-15", vintage)
        self.assertEqual(1, len(clean))
        self.assertEqual(["unmatched"], [r["reason"] for r in review])
        row = clean[0]
        self.assertIsNone(row["ds_redraft_one_ppr"])
        self.assertEqual(81.0, row["ds_redraft_half_ppr"])
        self.assertEqual(70.0, row["ds_values"]["dynasty_half_ppr"])
        self.assertEqual("2026-10-15", row["draftsharks_snapshot_date"])
        clean, _, _ = fs.build_rows(snapshot(self.tmp.name, FS_ROWS))
        self.assertIsNone(clean[0]["ros_total_ppr"])
        self.assertEqual(170.0, clean[0]["ros_total_half_ppr"])
        self.assertEqual(2026, clean[0]["season"])

    def test_empty_or_undated_snapshot_fails_closed(self):
        for mod, *_ in CASES:
            with self.assertRaises(SystemExit):
                mod.build_rows(snapshot(self.tmp.name, []))
            p = Path(self.tmp.name) / "nodate.json"
            p.write_text(json.dumps({"rows": [{"player_name": "x"}]}))
            with self.assertRaises(SystemExit):
                mod.build_rows(p)

    def _conflict_snapshot(self):
        players = PLAYERS + [{"player_key": 3001, "full_name": "Max Bredeson", "position": "TE", "active": True}]
        fs.fetch_players = lambda: players
        rows = FS_ROWS + [{"player_name": "Max Bredeson", "player_norm": "max bredeson", "pos": "RB", "team": "SF",
                           "fantasysharks_id": 22, "pts": {"half_ppr": 5.0}}]
        return snapshot(self.tmp.name, rows)

    def test_position_conflict_stays_out_of_clean_rows(self):
        clean, review, _ = fs.build_rows(self._conflict_snapshot())
        self.assertEqual([2227], [r["player_key"] for r in clean])
        self.assertEqual(["position_conflict"], [r["reason"] for r in review])

    def test_main_saves_only_clean_rows_and_dry_run_never_writes(self):
        snap = self._conflict_snapshot()
        saved = []
        fs.upsert_rows = lambda table, rows, conflict: saved.append(rows)
        fs.count_rows = lambda table, params: len(saved[0])
        for name in ("upsert_rows", "count_rows"):
            self.addCleanup(setattr, fs, name, getattr(fs, name))
        with mock.patch.object(fs.identity_queue, "record_misses"), \
                mock.patch.object(sys, "argv", ["x", "--snapshot", str(snap), "--dry-run"]), \
                contextlib.redirect_stdout(io.StringIO()):
            fs.main()
        self.assertEqual([], saved)
        out = io.StringIO()
        with mock.patch.object(fs.identity_queue, "record_misses"), \
                mock.patch.object(sys, "argv", ["x", "--snapshot", str(snap)]), \
                contextlib.redirect_stdout(out):
            fs.main()
        self.assertEqual([[2227]], [[r["player_key"] for r in rows] for rows in saved])
        self.assertIn("REVIEW, NOT SAVED: position_conflict: Max Bredeson", out.getvalue())

    def test_duplicate_player_key_saves_neither_row(self):
        fs.fetch_players = lambda: PLAYERS
        dup = dict(FS_ROWS[0], fantasysharks_id=99, pts={"half_ppr": 1.0})
        clean, review, _ = fs.build_rows(snapshot(self.tmp.name, FS_ROWS + [dup]))
        self.assertEqual([], clean)
        self.assertEqual(["duplicate_player_key"] * 2, [r["reason"] for r in review])


if __name__ == "__main__":
    unittest.main()
