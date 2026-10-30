"""JEG-621: direct Postgres hooks for the Fantasy Sharks saver. Hermetic, no live DB."""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
import pg_direct  # noqa: E402


class FakeCursor:
    def __init__(self, log, fetch=None, desc=None):
        self.log, self._fetch, self.description = log, fetch or [], desc

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, sql, args=None): self.log.append(("execute", sql, args))
    def executemany(self, sql, seq): self.log.append(("executemany", sql, list(seq)))
    def fetchall(self): return self._fetch
    def fetchone(self): return self._fetch[0]


class FakeConn:
    def __init__(self, fetch=None, desc=None):
        self.log, self._fetch, self._desc = [], fetch, desc

    def __enter__(self): return self
    def __exit__(self, *a): return False
    def cursor(self): return FakeCursor(self.log, self._fetch, self._desc)
    def commit(self): self.log.append(("commit",))


class PgDirectTest(unittest.TestCase):
    def test_upsert_sql_updates_non_conflict_columns(self):
        sql = pg_direct.upsert_sql("t", ["player_key", "d", "v"], "player_key,d")
        self.assertIn('on conflict ("player_key", "d") do update set "v" = excluded."v"', sql)
        self.assertNotIn('"d" = excluded', sql)

    def test_unsafe_identifier_rejected(self):
        with self.assertRaises(ValueError):
            pg_direct.upsert_sql("t; drop table x", ["a"], "a")

    def test_upsert_batches_and_commits(self):
        conn = FakeConn()
        rows = [{"player_key": i, "d": "2026-10-30", "v": None} for i in range(1200)]
        pg_direct.upsert_rows("t", rows, "player_key,d", connect_fn=lambda: conn)
        batches = [e for e in conn.log if e[0] == "executemany"]
        self.assertEqual([len(b[2]) for b in batches], [500, 500, 200])
        self.assertIsNone(batches[0][2][0][2])  # null stays null
        self.assertEqual(conn.log[-1], ("commit",))

    def test_count_sql_decodes_rest_filters(self):
        sql, args = pg_direct.count_sql("t", "?select=id&snap=eq.2026-10-30&pulled_at=eq.2026-10-30T10%3A00%3A00%2B00%3A00")
        self.assertEqual(sql, 'select count(*) from public."t" where "snap" = %s and "pulled_at" = %s')
        self.assertEqual(args, ["2026-10-30", "2026-10-30T10:00:00+00:00"])

    def test_count_rows_returns_int(self):
        conn = FakeConn(fetch=[(477,)])
        self.assertEqual(pg_direct.count_rows("t", "?select=id&a=eq.1", connect_fn=lambda: conn), 477)

    def test_fetch_players_maps_columns(self):
        desc = [mock.Mock(), mock.Mock()]
        desc[0].name, desc[1].name = "player_key", "full_name"
        conn = FakeConn(fetch=[(1, "A B")], desc=desc)
        self.assertEqual(pg_direct.fetch_players(connect_fn=lambda: conn), [{"player_key": 1, "full_name": "A B"}])

    def test_missing_keychain_item_fails_closed_without_leaking(self):
        bad = mock.Mock(returncode=44, stdout="", stderr="")
        with mock.patch.object(pg_direct.subprocess, "run", return_value=bad):
            with self.assertRaises(SystemExit) as cm:
                pg_direct.read_db_url()
        self.assertIn("Keychain", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
