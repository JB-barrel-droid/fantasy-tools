#!/usr/bin/env python3
"""JEG-671: RotoBaller saver and draft migration 011. Hermetic: no network, no DB.

Pins: the saver writes only columns the migration creates; the upsert key is a unique index; the
migration only creates and enables RLS; 0 or missing stays null (never zero); vintage is the
snapshot date; unmatched names go to review; a bad snapshot (no rows, no date, no or wrong
fingerprint, wrong source, out-of-range value) fails closed; dry run is the default and writes
nothing; credentials come from the environment only and a missing one fails closed.
"""
import contextlib
import copy
import io
import json
import os
import re
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import pull_rotoballer as pull  # noqa: E402
import save_rotoballer_references as sv  # noqa: E402

TABLE = "rotoballer_trade_values"
MIGRATION = ROOT / "sql" / "migrations" / "011_rotoballer_trade_values.sql"
PLAYERS = [
    {"player_key": 101, "full_name": "Bijan Robinson", "position": "RB", "active": True},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB", "active": True},
]
EXPECTED_NORMS = {p["full_name"].lower() for p in PLAYERS}
BODY = (ROOT / "tests" / "fixtures" / "rotoballer_week5_sample.html").read_text(encoding="utf-8")


def fixture_snapshot():
    return pull.build_snapshot(BODY, "https://example.test/week5", today=date(2026, 10, 9),
                               now=datetime(2026, 10, 9, 12, tzinfo=timezone.utc))


def table_columns(sql):
    body = sql.split("CREATE TABLE IF NOT EXISTS public." + TABLE + " (", 1)[1].split("\n);", 1)[0]
    cols = set()
    for line in body.splitlines():
        m = re.match(r"([a-z_0-9]+)\s+[A-Z]", line.split("--", 1)[0].strip())
        if m:
            cols.add(m.group(1))
    return cols


class SaveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name in ("fetch_players", "upsert_rows", "count_rows"):
            self.addCleanup(setattr, sv, name, getattr(sv, name))
        sv.fetch_players = lambda: PLAYERS
        self.calls = []
        sv.upsert_rows = lambda *a: self.calls.append(a)
        self.snap = fixture_snapshot()

    def path(self, snap=None, name="snapshot.json"):
        p = Path(self.tmp.name) / name
        p.write_text(json.dumps(snap if snap is not None else self.snap), encoding="utf-8")
        return p

    def build(self, snap=None):
        return sv.build_rows(self.path(snap))

    def refingerprint(self, snap):
        snap["fingerprint"] = sv.fingerprint_of(snap["rows"])
        return snap

    def src_row(self, snap, norm):
        return next(r for r in snap["rows"] if r["player_norm"] == norm)

    def row_for(self, norm, snap=None):
        clean, _, _ = self.build(snap)
        return next(r for r in clean if r["player_norm"] == norm)

    def test_fixture_fingerprint_matches_puller_recipe(self):
        self.assertEqual(self.snap["fingerprint"], sv.fingerprint_of(self.snap["rows"]))

    def test_saver_writes_only_migration_columns_and_key_is_unique(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        clean, _, _ = self.build()
        written = set().union(*(r.keys() for r in clean))
        self.assertEqual(set(), written - table_columns(sql))
        self.assertEqual(TABLE, sv.TABLE)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS rotoballer_trade_values_player_date_uidx", sql)
        self.assertEqual(f"player_key,{sv.SNAPSHOT_COLUMN}", sv.CONFLICT)
        self.assertIn("(player_key, rotoballer_snapshot_date)", sql)

    def test_migration_only_creates_and_enables_rls(self):
        lines = [l.strip() for l in MIGRATION.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("--")]
        self.assertEqual(1, sum(l.startswith("CREATE TABLE") for l in lines))
        for line in lines:
            if line.upper().startswith("ALTER TABLE"):
                self.assertEqual("ALTER TABLE public." + TABLE + " ENABLE ROW LEVEL SECURITY;", line)
            self.assertFalse(line.upper().startswith(("DROP ", "DELETE ", "TRUNCATE ")), line)
        self.assertIn("NOT APPLIED", MIGRATION.read_text(encoding="utf-8"))

    def test_row_building_values_vintage_and_identity(self):
        clean, review, vintage = self.build()
        self.assertEqual(self.snap["vintage_date"], vintage)
        self.assertEqual(EXPECTED_NORMS, {r["player_norm"] for r in clean})
        self.assertTrue(review)  # skill players not in PLAYERS are reviewed, never guessed
        self.assertTrue(all(r["reason"] == "unmatched" for r in review))
        row = self.row_for("jahmyr gibbs")
        src = self.src_row(self.snap, "jahmyr gibbs")
        self.assertEqual(2227, row["player_key"])
        self.assertEqual(vintage, row["rotoballer_snapshot_date"])
        self.assertEqual(self.snap["fingerprint"], row["fingerprint"])
        self.assertEqual("save_rotoballer_references.py", row["_writer_identity"])
        self.assertIn(self.snap["fingerprint"], row["_run_id"])
        self.assertEqual(src["trade_value"], row["rb_trade_value"])
        self.assertEqual(src["rank"], row["rb_rank"])
        self.assertEqual(src["rotoballer_id"], row["rotoballer_id"])
        self.assertEqual(5, row["article_week"])
        self.assertEqual(2026, row["season"])
        self.assertIsNone(row["scoring"])  # the source does not say; never guessed

    def test_zero_and_missing_stay_null_never_zero(self):
        snap = copy.deepcopy(self.snap)
        src = self.src_row(snap, "jahmyr gibbs")
        src["trade_value"] = 0
        self.refingerprint(snap)
        row = self.row_for("jahmyr gibbs", snap)
        self.assertIsNone(row["rb_trade_value"])
        self.assertIsNone(row["rb_rank"])
        self.assertIsNotNone(self.row_for("bijan robinson", snap)["rb_trade_value"])
        for r in self.build(snap)[0]:
            for col, val in r.items():
                if col.endswith(("_value", "_rank", "_tier", "_points")) or col in ():
                    self.assertNotEqual(0, val, col)

    def test_duplicate_player_goes_to_review(self):
        snap = copy.deepcopy(self.snap)
        dup = copy.deepcopy(self.src_row(snap, "jahmyr gibbs"))
        dup["rotoballer_id"] = 99999
        dup["pos"] = "RB"
        snap["rows"].append(dup)
        self.refingerprint(snap)
        clean, review, _ = self.build(snap)
        self.assertEqual(1, sum(r["player_norm"] == "jahmyr gibbs" for r in clean))
        self.assertIn("duplicate_player_key", [r["reason"] for r in review])

    def test_bad_snapshot_fails_closed(self):
        def bad(mutate):
            snap = copy.deepcopy(self.snap)
            mutate(snap)
            with self.assertRaises(SystemExit):
                self.build(snap)

        bad(lambda s: s.update(rows=[]))
        bad(lambda s: s.pop("vintage_date"))
        bad(lambda s: s.update(vintage_date="10/16/2026"))
        bad(lambda s: s.pop("fingerprint"))
        bad(lambda s: s.update(fingerprint="0" * 16))  # rows moved but fingerprint did not
        bad(lambda s: s.update(source="other"))
        bad(lambda s: s.update(schema="other_v9"))

        def out_of_range(s):
            s["rows"][0]["trade_value"] = 150
            self.refingerprint(s)
        bad(out_of_range)

    def test_dry_run_is_default_and_writes_nothing(self):
        sv.count_rows = lambda *a: self.fail("dry run must not count")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            sv.main(["--snapshot", str(self.path())])
        self.assertEqual([], self.calls)
        self.assertIn("[dry-run]", out.getvalue())

    def test_write_upserts_and_verifies_count(self):
        sv.count_rows = lambda table, params: len(sv.build_rows(self.path())[0])
        miss = []
        self.addCleanup(setattr, sv.identity_queue, "record_misses", sv.identity_queue.record_misses)
        sv.identity_queue.record_misses = lambda src, rows: miss.append((src, len(rows)))
        with contextlib.redirect_stdout(io.StringIO()):
            sv.main(["--snapshot", str(self.path()), "--write"])
        self.assertEqual(1, len(self.calls))
        self.assertEqual((TABLE, sv.CONFLICT), (self.calls[0][0], self.calls[0][2]))
        self.assertEqual("rotoballer", miss[0][0])

    def test_write_with_short_count_fails_closed(self):
        sv.count_rows = lambda *a: 0
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            sv.main(["--snapshot", str(self.path()), "--write"])

    def test_write_with_zero_clean_rows_fails_closed(self):
        sv.fetch_players = lambda: [{"player_key": 7, "full_name": "Someone Else", "position": "WR", "active": True}]
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            sv.main(["--snapshot", str(self.path()), "--write"])
        self.assertEqual([], self.calls)

    def test_credentials_come_from_env_only_and_missing_fails_closed(self):
        saved = {k: os.environ.pop(k, None) for k in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")}
        self.addCleanup(lambda: [os.environ.__setitem__(k, v) for k, v in saved.items() if v is not None])
        with self.assertRaises(SystemExit):
            sv._default_fetch_players()
        os.environ["SUPABASE_URL"] = "https://example.invalid"
        with self.assertRaises(SystemExit):  # key still missing: fails before any request
            sv._default_upsert(TABLE, [{"x": 1}], sv.CONFLICT)
        os.environ.pop("SUPABASE_URL")
        src = (ROOT / "pipelines" / "save_rotoballer_references.py").read_text(encoding="utf-8")
        self.assertNotIn("sbclient", src)
        self.assertNotIn("expanduser", src)


if __name__ == "__main__":
    unittest.main()
