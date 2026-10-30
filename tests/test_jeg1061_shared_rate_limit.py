"""JEG-1061: the get-values compute limit can be counted across function instances.

* The handler check (tests/node/get_values_shared_rate_limit_check.mjs): two instances of the deployed
  handler share one count when DDF_SHARED_RATE_LIMIT=1, fall back to the in-memory count when the database
  fails, and make no database call when the secret is off.
* The migration (supabase/migrations/jeg1061_shared_rate_limit_20261030.sql) against a throwaway local
  Postgres (skipped when no Postgres binaries are installed): edge_rate_hit counts a fixed window per key,
  only service_role may call it, nobody reads the table through the API roles, and the rollback removes both.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/jeg1061_shared_rate_limit_20261030.sql"
ROLLBACK = ROOT / "supabase/rollbacks/jeg1061_shared_rate_limit_rollback_20261030.sql"
PORT = "54361"


class HandlerTest(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_shared_limit_across_instances(self):
        from tests import _render_env
        _render_env.ensure_built()
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/get_values_shared_rate_limit_check.mjs"), str(ROOT / "dist")],
            capture_output=True, text=True, timeout=300, cwd=str(ROOT),
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


class StaticTest(unittest.TestCase):
    def test_migration_shape(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("NOT APPLIED", sql)
        self.assertIn("security definer", sql)
        self.assertIn("set search_path = public, pg_temp", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("from public, anon, authenticated", sql)
        self.assertIn("to service_role", sql)
        rollback = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn("drop function if exists public.edge_rate_hit(text, integer, integer)", rollback)
        self.assertIn("drop table if exists public.edge_rate_buckets", rollback)

    def test_off_by_default(self):
        src = (ROOT / "supabase/functions/get-values/rate-limit.ts").read_text(encoding="utf-8")
        self.assertIn('opts.env("DDF_SHARED_RATE_LIMIT") !== "1"', src)


def _pg_bindir():
    for cand in [os.environ.get("PG_BINDIR", "")] + sorted(
            (str(p) for p in Path("/usr/lib/postgresql").glob("*/bin")), reverse=True):
        if cand and (Path(cand) / "initdb").exists():
            return cand
    found = shutil.which("initdb")
    return str(Path(found).parent) if found else None


BINDIR = _pg_bindir()


@unittest.skipUnless(BINDIR, "no local Postgres binaries; the static checks still ran")
class PostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="jeg1061-pg-")
        cls.data = os.path.join(cls.dir, "data")
        cls.prefix = []
        if os.geteuid() == 0:  # initdb refuses root; run as the postgres user
            shutil.chown(cls.dir, user="postgres")
            os.chmod(cls.dir, 0o755)
            cls.prefix = ["runuser", "-u", "postgres", "--"]
        run = lambda args: subprocess.run(cls.prefix + args, check=True, capture_output=True, text=True)
        run([f"{BINDIR}/initdb", "-D", cls.data, "-A", "trust", "-U", "postgres", "--no-sync"])
        run([f"{BINDIR}/pg_ctl", "-D", cls.data, "-w", "-l", os.path.join(cls.dir, "log"),
             "-o", f"-k {cls.dir} -c listen_addresses='' -p {PORT}", "start"])
        cls.psql("create role anon nologin; create role authenticated nologin; create role service_role nologin;")
        cls.psql(MIGRATION.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        try:
            subprocess.run(cls.prefix + [f"{BINDIR}/pg_ctl", "-D", cls.data, "-m", "immediate", "stop"],
                           capture_output=True)
        finally:
            shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def psql(cls, sql, ok=True):
        res = subprocess.run(cls.prefix + [f"{BINDIR}/psql", "-h", cls.dir, "-p", PORT, "-U", "postgres",
                                           "-d", "postgres", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1"],
                             input=sql, capture_output=True, text=True)
        if ok and res.returncode != 0:
            raise AssertionError(f"psql failed: {res.stderr}")
        return res

    def hit(self, bucket, role="service_role", limit=10, window=60):
        res = self.psql(f"set role {role}; select public.edge_rate_hit('{bucket}', {limit}, {window});", ok=False)
        if res.returncode != 0:
            return "denied" if "permission denied" in res.stderr else res.stderr.strip()
        return res.stdout.strip()

    def test_fixed_window_per_bucket(self):
        got = [self.hit("a" * 64) for _ in range(11)]
        self.assertEqual(got, ["t"] * 10 + ["f"])
        self.assertEqual(self.hit("b" * 64), "t", "another bucket has its own count")
        # The window ends: the next hit starts a new one.
        self.psql(f"update public.edge_rate_buckets set window_start = now() - interval '61 seconds' "
                  f"where bucket = '{'a' * 64}';")
        self.assertEqual(self.hit("a" * 64), "t")
        self.assertEqual(self.psql(f"select hits from public.edge_rate_buckets where bucket = '{'a' * 64}';")
                         .stdout.strip(), "1")

    def test_only_service_role(self):
        for role in ("anon", "authenticated"):
            self.assertEqual(self.hit("c" * 64, role=role), "denied")
            res = self.psql(f"set role {role}; select count(*) from public.edge_rate_buckets;", ok=False)
            self.assertIn("permission denied", res.stderr)

    def test_bad_arguments_refused(self):
        self.assertIn("bad arguments", self.hit("", limit=10))
        self.assertIn("bad arguments", self.hit("d" * 64, limit=0))
        self.assertIn("bad arguments", self.hit("d" * 64, window=0))
        self.assertIn("bad arguments", self.hit("d" * 200))

    def test_zz_rollback_removes_everything(self):
        self.psql(ROLLBACK.read_text(encoding="utf-8"))
        res = self.psql("select to_regclass('public.edge_rate_buckets') is null, "
                        "to_regprocedure('public.edge_rate_hit(text, integer, integer)') is null;")
        self.assertEqual(res.stdout.strip(), "t|t")
        self.psql(MIGRATION.read_text(encoding="utf-8"))  # re-apply: the migration is idempotent


if __name__ == "__main__":
    unittest.main()
