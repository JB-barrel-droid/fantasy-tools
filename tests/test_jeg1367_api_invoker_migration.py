"""JEG-1367: pins the api.* security_invoker migration and its rollback.

Two layers:

* Static checks on the migration text (always run): every advisor view is
  flipped, the 4 functions are pinned, no data is written, no write policy is
  added, and the rollback undoes every policy and view the migration touches.
* A behaviour check against a throwaway local Postgres (skipped when no
  Postgres binaries are installed): the fixture copies the live grants, RLS
  and view definitions; every role (anon, authenticated, service_role) must see
  exactly the same rows through every api view before the migration, after it,
  and after the rollback. A mutated migration that only flips the views must
  change what anon sees, so the comparison is known to bite.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "supabase/migrations/jeg1367_api_views_security_invoker_20261030.sql"
ROLLBACK_PATH = ROOT / "supabase/rollbacks/jeg1367_api_views_security_invoker_rollback_20261030.sql"
FIXTURE_PATH = ROOT / "tests/fixtures/jeg1367_api_views_fixture.sql"
MIGRATION = MIGRATION_PATH.read_text(encoding="utf-8")
ROLLBACK = ROLLBACK_PATH.read_text(encoding="utf-8")

# The 11 views the advisor named on 2026-10-30, plus product_snapshot_history
# (same definer default, no grants today).
ADVISOR_VIEWS = ("players", "product_options", "player_values", "product_snapshot", "v_current_weekly_signals",
                 "weekly_dashboard_status", "source_freshness", "source_inputs_weekly", "source_input_weeks",
                 "value_check_latest", "value_check_diff")
ALL_VIEWS = ADVISOR_VIEWS + ("product_snapshot_history",)
ADVISOR_FUNCTIONS = ("public.weekly_fantasypros_raw_append_only()", "public.weekly_fantasypros_batches_guard()",
                     "public.weekly_fantasypros_pages_guard()", "public.value_check_prune(interval)")
ROLES = ("anon", "authenticated", "service_role")


def sql_only(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def migration_problems(sql):
    s = sql_only(sql)
    out = []
    for v in ALL_VIEWS:
        if not re.search(rf"alter view api\.{v}\s+set \(security_invoker = true\)", s):
            out.append(f"api.{v}: still runs as its owner")
    for f in ADVISOR_FUNCTIONS:
        if not re.search(rf"alter function {re.escape(f)}\s+set search_path = ", s):
            out.append(f"{f}: search_path not pinned")
    if re.search(r"\b(insert into|update\s+\w+\.\w+\s+set|delete from|truncate)\b", s, re.I):
        out.append("the migration writes data")
    if re.search(r"\b(drop|create or replace) (view|table|function)\b", s, re.I):
        out.append("the migration replaces or drops an object")
    if re.search(r"create policy[^;]*for (insert|update|delete|all)\b", s, re.I):
        out.append("a write policy was added")
    if re.search(r"grant (insert|update|delete|truncate|all)\b", s, re.I):
        out.append("a write grant was added")
    if re.search(r"grant select on public\.\w+ to anon", s):
        out.append("anon got a table-wide grant (column grants only)")
    return out


def rollback_problems(migration, rollback):
    m, r = sql_only(migration), sql_only(rollback)
    flat = re.sub(r"\s+", " ", r)
    out = []
    for name, table in re.findall(r"create policy (\w+) on (public\.\w+)", m):
        if f"drop policy if exists {name} on {table};" not in r:
            out.append(f"rollback leaves policy {name} on {table}")
    for v in re.findall(r"alter view (api\.\w+)\s+set \(security_invoker = true\)", m):
        if not re.search(rf"alter view {re.escape(v)}\s+(set \(security_invoker = false\)|reset \(security_invoker\))", r):
            out.append(f"rollback leaves {v} as security_invoker")
    for f in re.findall(r"alter function (\S+)\s+set search_path", m):
        if not re.search(rf"alter function {re.escape(f)}\s+reset search_path", r):
            out.append(f"rollback leaves search_path pinned on {f}")
    for cols, table in re.findall(r"grant select \(([^)]*)\)\s+on (public\.\w+) to", m):
        cols = re.sub(r"\s+", " ", cols)
        if f"revoke select ({cols}) on {table} from" not in flat:
            out.append(f"rollback leaves the column grant on {table}")
    if "revoke select on public.value_check_runs from authenticated;" in m \
            and "grant select on public.value_check_runs to authenticated;" not in r:
        out.append("rollback does not give authenticated its value_check_runs grant back")
    return out


class StaticMigrationTest(unittest.TestCase):
    def test_migration_is_complete(self):
        self.assertEqual([], migration_problems(MIGRATION))

    def test_rollback_undoes_the_migration(self):
        self.assertEqual([], rollback_problems(MIGRATION, ROLLBACK))

    def test_mutations_are_caught(self):
        cases = {
            "still runs as its owner": MIGRATION.replace(
                "alter view api.value_check_diff         set (security_invoker = true);", ""),
            "search_path not pinned": MIGRATION.replace(
                "alter function public.value_check_prune(interval)", "-- x"),
            "writes data": MIGRATION + "\ndelete from public.players;\n",
            "write policy": MIGRATION.replace("for select to anon using (true);", "for all to anon using (true);", 1),
            "table-wide grant": MIGRATION + "\ngrant select on public.players to anon;\n",
        }
        for want, mutated in cases.items():
            self.assertNotEqual(MIGRATION, mutated, want)
            self.assertTrue(any(want in p for p in migration_problems(mutated)), want)
        rb_cases = {
            "leaves policy": ROLLBACK.replace("drop policy if exists anon_read_api_20261030 on public.players;", ""),
            "as security_invoker": ROLLBACK.replace(
                "alter view api.players                  set (security_invoker = false);", ""),
            "search_path pinned": ROLLBACK.replace(
                "alter function public.value_check_prune(interval)          reset search_path;", ""),
            "grant back": ROLLBACK.replace("grant select on public.value_check_runs to authenticated;", ""),
        }
        for want, mutated in rb_cases.items():
            self.assertNotEqual(ROLLBACK, mutated, want)
            self.assertTrue(any(want in p for p in rollback_problems(MIGRATION, mutated)), want)


def _pg_bindir():
    for cand in [os.environ.get("PG_BINDIR", "")] + sorted(
            (str(p) for p in Path("/usr/lib/postgresql").glob("*/bin")), reverse=True):
        if cand and (Path(cand) / "initdb").exists():
            return cand
    found = shutil.which("initdb")
    return str(Path(found).parent) if found else None


PROBE = """
create or replace function pg_temp.probe(r text, v text) returns text language plpgsql as $$
declare res text;
begin
  begin
    execute format('set local role %I', r);
    execute format('select count(*) || '':'' || md5(coalesce(string_agg(t::text, ''|'' order by t::text), '''')) from %s t', v)
      into res;
    reset role;
  exception when insufficient_privilege then
    res := 'denied';
  end;
  return res;
end $$;
"""

STATE = """
select 'rel ' || n.nspname || '.' || c.relname || ' ' || coalesce((select string_agg(o, ',' order by o) from unnest(c.reloptions) o), '-') || ' ' || coalesce((select string_agg(x::text, ',' order by x::text) from unnest(c.relacl) x), '-')
  || ' ' || coalesce((select string_agg(a.attname || '=' || (select string_agg(x::text, ',' order by x::text) from unnest(a.attacl) x), ',' order by a.attname)
                      from pg_attribute a where a.attrelid = c.oid and a.attacl is not null), '-')
from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname in ('api', 'public') and c.relkind in ('r', 'v')
union all
select 'pol ' || tablename || ' ' || policyname || ' ' || cmd || ' ' || roles::text || ' ' || coalesce(qual, '') from pg_policies
union all
select 'fn ' || p.oid::regprocedure::text || ' ' || coalesce(p.proconfig::text, '-') from pg_proc p
  join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'public'
order by 1;
"""


class Cluster:
    """A throwaway Postgres on a unix socket in a temp dir."""

    def __init__(self, bindir):
        self.bindir = bindir
        self.dir = tempfile.mkdtemp(prefix="jeg1367-pg-")
        self.data = os.path.join(self.dir, "data")
        self.prefix = []
        if os.geteuid() == 0:  # initdb refuses root; run as the postgres user
            shutil.chown(self.dir, user="postgres")
            os.chmod(self.dir, 0o755)
            self.prefix = ["runuser", "-u", "postgres", "--"]

    def _run(self, args, **kw):
        return subprocess.run(self.prefix + args, check=True, capture_output=True, text=True, **kw)

    def start(self):
        self._run([f"{self.bindir}/initdb", "-D", self.data, "-A", "trust", "-U", "postgres", "--no-sync"])
        self._run([f"{self.bindir}/pg_ctl", "-D", self.data, "-w", "-l", os.path.join(self.dir, "log"),
                   "-o", f"-k {self.dir} -c listen_addresses='' -p 54367", "start"])

    def stop(self):
        try:
            self._run([f"{self.bindir}/pg_ctl", "-D", self.data, "-m", "immediate", "stop"])
        finally:
            shutil.rmtree(self.dir, ignore_errors=True)

    def psql(self, sql):
        res = subprocess.run(self.prefix + [f"{self.bindir}/psql", "-h", self.dir, "-p", "54367", "-U", "postgres",
                                            "-d", "postgres", "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1"],
                             input=sql, capture_output=True, text=True)
        if res.returncode != 0:
            raise AssertionError(f"psql failed: {res.stderr}")
        return res.stdout

    def snapshot(self):
        rows = [f"select '{r} {v} ' || pg_temp.probe('{r}', 'api.{v}');" for r in ROLES for v in ALL_VIEWS]
        out = self.psql(PROBE + "\n".join(rows))
        return dict(line.rsplit(" ", 1) for line in out.splitlines() if line.strip())

    def state(self):
        return self.psql(STATE)

    def as_role(self, role, sql):
        """Run one read as a role; 'denied' on a privilege error."""
        try:
            return self.psql(f"set role {role};\n{sql}").strip()
        except AssertionError as e:
            if "permission denied" in str(e):
                return "denied"
            raise


BINDIR = _pg_bindir()


@unittest.skipUnless(BINDIR, "no local Postgres binaries; the static checks still ran")
class LiveCopyBehaviourTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pg = Cluster(BINDIR)
        cls.pg.start()

    @classmethod
    def tearDownClass(cls):
        cls.pg.stop()

    def test_every_role_sees_the_same_rows_before_after_and_after_rollback(self):
        pg = self.pg
        pg.psql(FIXTURE_PATH.read_text(encoding="utf-8"))
        state_before = pg.state()
        before = pg.snapshot()
        # The fixture is meaningful: anon reads every advisor view today, and
        # the filters drop rows (inactive snapshot, old run, other product).
        for v in ADVISOR_VIEWS:
            self.assertNotEqual("denied", before[f"anon {v}"], v)
            self.assertFalse(before[f"anon {v}"].startswith("0:"), v)
        self.assertEqual("denied", before["anon product_snapshot_history"])
        self.assertTrue(before["authenticated value_check_diff"].startswith("2:"))

        pg.psql(MIGRATION)
        self.assertEqual(before, pg.snapshot())
        for v in ALL_VIEWS:
            self.assertIn("security_invoker=true", pg.psql(
                f"select reloptions::text from pg_class where oid = 'api.{v}'::regclass;"), v)
        for f in ADVISOR_FUNCTIONS:
            self.assertIn("search_path=public, pg_temp", pg.psql(
                f"select proconfig::text from pg_proc where oid = '{f}'::regprocedure;"), f)
        # Direct base-table reads stay inside what the views already show.
        self.assertEqual("denied", pg.as_role("anon", "select id from public.players;"))
        self.assertEqual("denied", pg.as_role("anon", "select bake_uuid from public.consolidated_values;"))
        self.assertEqual("denied", pg.as_role("anon", "select report from public.value_check_runs;"))
        self.assertEqual("denied", pg.as_role("authenticated", "select report from public.value_check_runs;"))
        self.assertEqual("denied", pg.as_role("anon", "select inserted_at from public.product_snapshot;"))
        self.assertEqual("1", pg.as_role("anon", "select count(*) from public.product_snapshot;"))
        self.assertEqual("1", pg.as_role("anon", "select count(*) from public.product_options;"))
        self.assertEqual("1", pg.as_role("anon", "select count(*) from public.weekly_dashboard_signals;"))
        self.assertEqual("denied", pg.as_role("anon", "insert into public.players (player_key) values (1);"))

        pg.psql(ROLLBACK)
        self.assertEqual(before, pg.snapshot())
        self.assertEqual(state_before, pg.state())

        # The comparison bites: flipping the views without part 1 changes what
        # anon sees (it loses eight views) and authenticated (value_check rows).
        flips = "\n".join(l for l in MIGRATION.splitlines() if l.startswith("alter view api."))
        pg.psql(flips)
        flipped_only = pg.snapshot()
        self.assertNotEqual(before, flipped_only)
        self.assertEqual("denied", flipped_only["anon players"])
        self.assertEqual("denied", flipped_only["anon value_check_diff"])
        self.assertTrue(flipped_only["authenticated value_check_diff"].startswith("0:"))


if __name__ == "__main__":
    unittest.main()
