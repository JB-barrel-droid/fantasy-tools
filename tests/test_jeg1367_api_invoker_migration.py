"""JEG-1367 / JEG-1374: pins the api.* security_invoker migration and rollback.

Two layers:

* Static checks on the migration text (always run): the 6 views whose access
  a column grant and row policy can match exactly are flipped, the 5 that
  cannot are left definer with no new grant or policy on their tables, the 4
  functions are pinned, no data is written, no write policy is added, and the
  rollback undoes every policy, grant and view the migration touches.
* A behaviour check against a throwaway local Postgres (skipped when no
  Postgres binaries are installed): the fixture copies the live grants, RLS
  and view definitions; every role (anon, authenticated, service_role) must see
  exactly the same rows through every api view before the migration, after it,
  and after the rollback, and anon's direct read of each newly granted table
  must equal its view. A mutated migration that only flips the views must
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

# Flipped: a column grant plus the view's own row filter reproduces the view
# exactly. product_snapshot_history has the definer default but no grants.
FLIPPED = ("product_options", "product_snapshot", "value_check_diff", "source_freshness",
           "source_inputs_weekly", "source_input_weeks", "product_snapshot_history")
# Kept definer (JEG-1374): no grant + policy matches them (jsonb read by key, a
# join on a hidden column, a latest-row filter), so they stay owner-rights.
KEPT_DEFINER = ("players", "player_values", "v_current_weekly_signals", "weekly_dashboard_status",
                "value_check_latest")
# Tables only the kept views need: the migration must not open them.
KEPT_TABLES = ("players", "consolidated_values", "weekly_dashboard_runs", "weekly_dashboard_signals",
               "value_check_runs")
ALL_VIEWS = FLIPPED + KEPT_DEFINER
ADVISOR_FUNCTIONS = ("public.weekly_fantasypros_raw_append_only()", "public.weekly_fantasypros_batches_guard()",
                     "public.weekly_fantasypros_pages_guard()", "public.value_check_prune(interval)")
ROLES = ("anon", "authenticated", "service_role")


def sql_only(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def migration_problems(sql):
    s = sql_only(sql)
    out = []
    for v in FLIPPED:
        if not re.search(rf"alter view api\.{v}\s+set \(security_invoker = true\)", s):
            out.append(f"api.{v}: still runs as its owner")
    for v in KEPT_DEFINER:
        if re.search(rf"alter view api\.{v}\b", s):
            out.append(f"api.{v}: changed, but no grant and policy can match what it shows")
    for t in KEPT_TABLES:
        if re.search(rf"(grant|revoke)[^;]*on public\.{t}\b|create policy[^;]*on public\.{t}\b", s):
            out.append(f"public.{t}: opened, but only a definer view needs it")
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
            "no grant and policy can match": MIGRATION.replace(
                "alter view api.value_check_diff", "alter view api.players set (security_invoker = true);\nalter view api.value_check_diff"),
            "only a definer view needs it": MIGRATION + "\ngrant select (player_key) on public.players to anon;\n",
            "search_path not pinned": MIGRATION.replace(
                "alter function public.value_check_prune(interval)", "-- x"),
            "writes data": MIGRATION + "\ndelete from public.product_options;\n",
            "write policy": MIGRATION.replace("for select to anon using (true);", "for all to anon using (true);", 1),
            "table-wide grant": MIGRATION + "\ngrant select on public.product_options to anon;\n",
        }
        for want, mutated in cases.items():
            self.assertNotEqual(MIGRATION, mutated, want)
            self.assertTrue(any(want in p for p in migration_problems(mutated)), want)
        rb_cases = {
            "leaves policy": ROLLBACK.replace(
                "drop policy if exists anon_read_api_published_20261030 on public.product_snapshot;", ""),
            "as security_invoker": ROLLBACK.replace(
                "alter view api.product_snapshot         set (security_invoker = false);", ""),
            "search_path pinned": ROLLBACK.replace(
                "alter function public.value_check_prune(interval)          reset search_path;", ""),
            "column grant": ROLLBACK.replace("  on public.value_check_values from anon;", "  on public.teams from anon;"),
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
        # the filters drop rows (inactive and unpublishable snapshots, an old
        # run, another product).
        for v in ALL_VIEWS:
            if v == "product_snapshot_history":
                continue
            self.assertNotEqual("denied", before[f"anon {v}"], v)
            self.assertFalse(before[f"anon {v}"].startswith("0:"), v)
        self.assertEqual("denied", before["anon product_snapshot_history"])
        self.assertTrue(before["authenticated value_check_diff"].startswith("2:"))

        pg.psql(MIGRATION)
        self.assertEqual(before, pg.snapshot())
        for v in FLIPPED:
            self.assertIn("security_invoker=true", pg.psql(
                f"select reloptions::text from pg_class where oid = 'api.{v}'::regclass;"), v)
        for v in KEPT_DEFINER:
            self.assertNotIn("security_invoker=true", pg.psql(
                f"select coalesce(reloptions::text, '') from pg_class where oid = 'api.{v}'::regclass;"), v)
        for f in ADVISOR_FUNCTIONS:
            self.assertIn("search_path=public, pg_temp", pg.psql(
                f"select proconfig::text from pg_proc where oid = '{f}'::regprocedure;"), f)
        self.assert_direct_reads_equal_views(pg)

        pg.psql(ROLLBACK)
        self.assertEqual(before, pg.snapshot())
        self.assertEqual(state_before, pg.state())

        # The comparison bites: flipping the views without part 1 changes what
        # anon sees (product_options, product_snapshot, value_check_diff) and
        # what authenticated sees (value_check_diff rows).
        flips = "\n".join(l for l in MIGRATION.splitlines() if l.startswith("alter view api."))
        pg.psql(flips)
        flipped_only = pg.snapshot()
        self.assertNotEqual(before, flipped_only)
        for v in ("product_options", "product_snapshot", "value_check_diff"):
            self.assertEqual("denied", flipped_only[f"anon {v}"], v)
        self.assertTrue(flipped_only["authenticated value_check_diff"].startswith("0:"))

    # The row filter of the view each granted table serves. A grant on a table
    # missing here fails the test, so every new grant names its view's filter.
    VIEW_FILTERS = {
        "product_options": "product_key = 'default'",
        "product_snapshot": "is_active and publishable",
        "value_check_values": "true",
    }

    def assert_direct_reads_equal_views(self, pg):
        grants = re.findall(r"grant select \(([^)]*)\)\s+on public\.(\w+) to ([\w, ]+);", sql_only(MIGRATION))
        self.assertEqual(set(self.VIEW_FILTERS), {t for _, t, _ in grants})
        digest = "select count(*) || ':' || md5(coalesce(string_agg(t::text, '|' order by t::text), '')) from ({q}) t;"
        for cols, table, roles in grants:
            cols = re.sub(r"\s+", " ", cols).strip()
            want = pg.psql(digest.format(q=f"select {cols} from public.{table} where {self.VIEW_FILTERS[table]}")).strip()
            hidden = pg.psql(
                f"select string_agg(column_name, ',') from information_schema.columns where table_schema = 'public' "
                f"and table_name = '{table}' and column_name not in "
                f"({', '.join(repr(c.strip()) for c in cols.split(','))});").strip()
            for role in ("anon", "authenticated"):
                got = pg.as_role(role, digest.format(q=f"select {cols} from public.{table}"))
                if role in roles or (role == "authenticated" and table == "value_check_values"):
                    self.assertEqual(want, got, f"{role} reads more of {table} than its view shows")
                for col in filter(None, hidden.split(",")):
                    if role in roles:
                        self.assertEqual("denied", pg.as_role(role, f"select {col} from public.{table};"), col)
        # Tables only the definer views need stay closed to anon.
        for t in KEPT_TABLES:
            self.assertEqual("denied", pg.as_role("anon", f"select count(*) from public.{t};"), t)
        self.assertEqual("denied", pg.as_role("anon", "insert into public.product_options (product_key) values ('x');"))


if __name__ == "__main__":
    unittest.main()
