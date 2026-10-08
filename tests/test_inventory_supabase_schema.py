"""Tests for pipelines/inventory_supabase_schema.py (JEG-111).

The script is a read-only schema inventory. The tests verify the parser
and the subproject grouping with synthetic SQL fixtures (so we never
depend on the live Supabase schema for correctness), and also verify
that the script runs against the real repo's ``sql/migrations/*.sql``
directory and produces a JSON document.

Each test targets one way the script could silently break:
  * A CREATE TABLE / VIEW / FUNCTION / TRIGGER with comments and
    dollar-quoted PL/pgSQL bodies must be found.
  * The grouping heuristic must classify trade-value, waiver-wire,
    lottery/fds, razzball, cbs-ros, and shared/reference correctly, and
    must NOT invent a subproject for unclassifiable objects.
  * The script must not import any DB client (read-only by construction).
  * The script must run end-to-end against the real repo and emit JSON.
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))
import inventory_supabase_schema as inv  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _name_set(group):
    """Return the set of object names declared in a by-subproject group."""

    return {item["name"] for item in group}


def _kind_set(group):
    """Return the set of object kinds declared in a by-subproject group."""

    return {item["kind"] for item in group}


# ---------------------------------------------------------------------------
# Parser unit tests (use synthetic SQL; do NOT touch the network or repo)
# ---------------------------------------------------------------------------


class ParserTests(unittest.TestCase):
    """Parser correctness: comment / string / dollar-quote stripping,
    and CREATE-statement extraction."""

    def test_strips_line_comments(self):
        sql = "-- CREATE TABLE foo (id int);\nCREATE TABLE bar (id int);"
        clean = inv._strip_comments_and_strings(sql)
        self.assertNotIn("foo", clean)
        # The non-commented CREATE TABLE bar must still match.
        self.assertIn("bar", clean)

    def test_strips_block_comments(self):
        sql = "/* CREATE TABLE foo (id int); */ CREATE TABLE bar (id int);"
        clean = inv._strip_comments_and_strings(sql)
        self.assertNotIn("foo", clean)
        self.assertIn("bar", clean)

    def test_strips_single_quoted_strings(self):
        sql = "INSERT INTO x VALUES ('CREATE TABLE bogus (id int)');"
        clean = inv._strip_comments_and_strings(sql)
        self.assertNotIn("bogus", clean)
        self.assertNotIn("CREATE", clean)

    def test_strips_dollar_quoted_bodies(self):
        sql = (
            "CREATE FUNCTION foo() RETURNS void AS $$ "
            "CREATE TABLE inside_dollar (id int); "
            "$$ LANGUAGE sql;\n"
            "CREATE TABLE bar (id int);\n"
        )
        clean = inv._strip_comments_and_strings(sql)
        # The CREATE inside the dollar-quoted body must NOT match.
        self.assertNotIn("inside_dollar", clean)
        self.assertIn("bar", clean)

    def test_keeps_create_keyword_outside_strings(self):
        sql = "CREATE TABLE public.foo (id int);"
        clean = inv._strip_comments_and_strings(sql)
        # The "CREATE" keyword survives outside string contexts.
        self.assertRegex(clean, r"CREATE\s+TABLE\s+public\.foo\s*\(")

    def test_extracts_create_table_if_not_exists(self):
        sql = "CREATE TABLE IF NOT EXISTS public.foo (id int);"
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [("TABLE", "public", "foo")])

    def test_extracts_create_view_or_replace(self):
        sql = "CREATE OR REPLACE VIEW public.foo AS SELECT 1;"
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [("VIEW", "public", "foo")])

    def test_extracts_create_materialized_view(self):
        sql = "CREATE MATERIALIZED VIEW public.foo AS SELECT 1;"
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [("VIEW", "public", "foo")])

    def test_extracts_create_function_with_schema(self):
        sql = "CREATE OR REPLACE FUNCTION public.foo() RETURNS void AS $$ $$ LANGUAGE sql;"
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [("FUNCTION", "public", "foo")])

    def test_extracts_create_trigger(self):
        sql = "CREATE TRIGGER foo BEFORE INSERT ON bar FOR EACH ROW EXECUTE FUNCTION baz();"
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [("TRIGGER", None, "foo")])

    def test_ignores_create_index(self):
        # INDEX is explicitly out of scope per the module docstring.
        sql = "CREATE UNIQUE INDEX foo_idx ON public.bar (id);"
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [])

    def test_ignores_alter_table(self):
        sql = (
            "ALTER TABLE public.foo ADD COLUMN bar int;\n"
            "DROP INDEX IF EXISTS public.foo_idx;\n"
        )
        kinds = inv._extract_objects(inv._strip_comments_and_strings(sql))
        self.assertEqual(kinds, [])


# ---------------------------------------------------------------------------
# Grouping heuristic tests (use the real ``_classify`` on synthetic names)
# ---------------------------------------------------------------------------


class GroupingTests(unittest.TestCase):
    """Subproject assignment based on filename + object name."""

    def test_trade_value_via_object_name(self):
        self.assertEqual(inv._classify("anything.sql", "source_trade_values"),
                         "trade-value")

    def test_trade_value_via_filename(self):
        # File name with "trade_value" hint, object is generic.
        self.assertEqual(inv._classify("005_source_trade_values_x.sql",
                                       "source_value_adjustments"),
                         "trade-value")

    def test_waiver_wire_via_vorp(self):
        self.assertEqual(inv._classify("jeg62.sql", "publisher_vorp"),
                         "waiver-wire")

    def test_waiver_wire_via_filename(self):
        self.assertEqual(inv._classify("001_lottery_tables.sql", "foo"),
                         "lottery/fds")

    def test_lottery_fds_via_object(self):
        self.assertEqual(inv._classify("anything.sql", "lottery_state"),
                         "lottery/fds")

    def test_razzball(self):
        self.assertEqual(inv._classify("003_razzball.sql", "razzball_projections"),
                         "razzball")

    def test_cbs_ros(self):
        self.assertEqual(inv._classify("002_cbs_ros_projections.sql",
                                       "cbs_ros_projections"),
                         "cbs-ros")

    def test_shared_reference_audit(self):
        self.assertEqual(inv._classify("001_pipeline_write_audit_repair.sql",
                                       "pipeline_write_audit"),
                         "shared/reference")

    def test_unclassified_is_never_a_guess(self):
        # A name with no matching needle MUST land in "unclassified".
        self.assertEqual(inv._classify("zz_mystery.sql", "mystery_table"),
                         "unclassified")


# ---------------------------------------------------------------------------
# Fixture-based aggregation test (build a temp tree, run build_inventory,
# assert the by-subproject layout).
# ---------------------------------------------------------------------------


_FIXTURE_SQL = {
    # Subproject: trade-value
    "sql/migrations/099_trade_value_bake.sql": (
        "-- 099: trade-value fixture\n"
        "CREATE UNIQUE INDEX IF NOT EXISTS src_trade_value_idx\n"
        "    ON public.source_trade_values (bake_id);\n"
        "CREATE OR REPLACE VIEW public.source_value_adjustments_v AS\n"
        "    SELECT * FROM public.source_value_adjustments;\n"
    ),
    # Subproject: cbs-ros (filename + object name both hint cbs-ros)
    "sql/migrations/100_cbs_ros_fixture.sql": (
        "CREATE TABLE IF NOT EXISTS public.cbs_ros_projections (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
    ),
    # Subproject: razzball
    "sql/migrations/101_razzball_fixture.sql": (
        "CREATE TABLE IF NOT EXISTS public.razzball_projections (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
    ),
    # Subproject: shared/reference
    "sql/migrations/102_audit_fixture.sql": (
        "CREATE TABLE IF NOT EXISTS public.pipeline_write_audit (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
    ),
    # Subproject: waiver-wire (vorp + roster)
    "sql/migrations/103_waiver_wire_fixture.sql": (
        "CREATE TABLE IF NOT EXISTS public.publisher_roster_assumptions (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
        "CREATE TABLE IF NOT EXISTS public.publisher_vorp (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
    ),
    # Subproject: lottery/fds
    "sql/migrations/104_lottery_fixture.sql": (
        "CREATE TABLE IF NOT EXISTS public.lottery_players (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
        "CREATE OR REPLACE FUNCTION public.fds_aggregate() RETURNS int\n"
        "    AS $$ SELECT 1 $$ LANGUAGE sql;\n"
    ),
    # Unclassified (no hint, no matching needle -> must NOT guess)
    "sql/migrations/105_unclassified_fixture.sql": (
        "CREATE TABLE IF NOT EXISTS public.mystery_table (\n"
        "    id uuid PRIMARY KEY DEFAULT gen_random_uuid()\n"
        ");\n"
        "CREATE OR REPLACE VIEW public.other_mystery AS SELECT 1;\n"
    ),
}


class FixtureAggregationTests(unittest.TestCase):
    """End-to-end ``build_inventory`` over a temp SQL tree."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        root = Path(cls.tmpdir.name)
        for rel, content in _FIXTURE_SQL.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        cls.root = root
        cls.inventory = inv.build_inventory([root])

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def test_totals_match_fixture_objects(self):
        # Tally expected object counts by kind from the fixture.
        # Each fixture SQL file declares the kinds listed in the table below.
        expected = {"TABLE": 7, "VIEW": 2, "FUNCTION": 1, "files": 7}
        # Function: fds_aggregate is the only FUNCTION.
        # Tables (7): cbs_ros_projections, razzball_projections,
        # pipeline_write_audit, publisher_roster_assumptions,
        # publisher_vorp, lottery_players, mystery_table.
        # Views (2): source_value_adjustments_v, other_mystery.
        for k, v in expected.items():
            with self.subTest(key=k):
                self.assertEqual(self.inventory["totals"][k], v)

    def test_trade_value_subproject(self):
        self.assertIn("trade-value", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["trade-value"])
        # The fixture file creates the VIEW source_value_adjustments_v (the
        # CREATE TABLE source_trade_values statement is not in the fixture;
        # only an INDEX on it is, and INDEX is out of scope).
        self.assertIn("source_value_adjustments_v", names)  # via filename
        self.assertIn("source_value_adjustments_v", names)  # via view name

    def test_cbs_ros_subproject(self):
        self.assertIn("cbs-ros", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["cbs-ros"])
        self.assertEqual(names, {"cbs_ros_projections"})

    def test_razzball_subproject(self):
        self.assertIn("razzball", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["razzball"])
        self.assertEqual(names, {"razzball_projections"})

    def test_shared_reference_subproject(self):
        self.assertIn("shared/reference", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["shared/reference"])
        self.assertEqual(names, {"pipeline_write_audit"})

    def test_waiver_wire_subproject(self):
        self.assertIn("waiver-wire", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["waiver-wire"])
        self.assertEqual(names, {"publisher_roster_assumptions",
                                 "publisher_vorp"})

    def test_lottery_fds_subproject(self):
        self.assertIn("lottery/fds", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["lottery/fds"])
        # lottery_players -> lottery match; fds_aggregate -> fds_ match.
        self.assertEqual(names, {"lottery_players", "fds_aggregate"})

    def test_unclassified_subproject_present(self):
        self.assertIn("unclassified", self.inventory["by_subproject"])
        names = _name_set(self.inventory["by_subproject"]["unclassified"])
        self.assertEqual(names, {"mystery_table", "other_mystery"})

    def test_files_table_reports_paths_and_kinds(self):
        # Every fixture file should appear in the files table.
        paths = {row["path"] for row in self.inventory["files"]}
        self.assertEqual(len(paths), len(_FIXTURE_SQL))
        # Kinds per file are sorted, distinct kinds only.
        for row in self.inventory["files"]:
            self.assertEqual(row["object_kinds"], sorted(set(row["object_kinds"])))

    def test_no_subproject_invents(self):
        # Every classified item must be in a real rule's subproject, OR in
        # "unclassified". Never a guess.
        self.assertNotIn("unknown", self.inventory["by_subproject"])
        self.assertNotIn("misc", self.inventory["by_subproject"])

    def test_schema_version_is_present(self):
        self.assertEqual(self.inventory["schema_version"],
                         "jeg111-schema-inventory-v1")


# ---------------------------------------------------------------------------
# Safety tests: read-only by construction.
# ---------------------------------------------------------------------------


class ReadOnlySafetyTests(unittest.TestCase):
    """The script must not import any DB client and must not open a socket."""

    def test_no_db_client_imports(self):
        # Scan the script source for known DB client import lines.
        src = (REPO_ROOT / "pipelines" / "inventory_supabase_schema.py").read_text(encoding="utf-8")
        for forbidden in ("supabase", "psycopg", "psycopg2", "asyncpg",
                          "sqlalchemy", "pymongo", "requests.", "urllib.request",
                          "httpx", "aiohttp"):
            with self.subTest(forbidden=forbidden):
                # 'urllib' alone is too noisy; match the call form.
                self.assertNotRegex(
                    src,
                    rf"(?im)^\s*(?:from|import)\s+.*{re.escape(forbidden)}.*$",
                )

    def test_no_socket_or_network_calls(self):
        src = (REPO_ROOT / "pipelines" / "inventory_supabase_schema.py").read_text(encoding="utf-8")
        for forbidden in ("socket.", "urlopen", "create_connection",
                          "HTTPSConnection", "HTTPConnection"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, src)


# ---------------------------------------------------------------------------
# Live end-to-end test: run the script against the real repo's migrations.
# ---------------------------------------------------------------------------


class LiveRepoRunTests(unittest.TestCase):
    """Run the script as a subprocess and verify the JSON output."""

    def test_script_runs_and_returns_json(self):
        # Skip if the repo's sql/migrations directory is absent (slim checkout).
        sql_dir = REPO_ROOT / "sql" / "migrations"
        if not sql_dir.exists():
            self.skipTest("sql/migrations not present in this checkout")

        result = subprocess.run(
            [sys.executable, str(PIPELINES / "inventory_supabase_schema.py"),
             "--root", str(sql_dir)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)

        # Schema-version sanity.
        self.assertEqual(payload["schema_version"], "jeg111-schema-inventory-v1")
        # The defaults include the supplied root in the roots list.
        self.assertIn(str(sql_dir), payload["roots"])

        # All declared subprojects are known (or "unclassified").
        allowed = {
            "trade-value", "waiver-wire", "lottery/fds",
            "razzball", "cbs-ros", "shared/reference", "unclassified",
        }
        for sub in payload["by_subproject"]:
            self.assertIn(sub, allowed)

        # Every by-subproject entry carries the required fields.
        for sub, items in payload["by_subproject"].items():
            for item in items:
                for key in ("kind", "schema", "name", "qualified_name", "file"):
                    self.assertIn(key, item, f"missing {key} in {sub}")

    def test_script_writes_to_out_flag(self):
        sql_dir = REPO_ROOT / "sql" / "migrations"
        if not sql_dir.exists():
            self.skipTest("sql/migrations not present in this checkout")
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "inv.json"
            result = subprocess.run(
                [sys.executable, str(PIPELINES / "inventory_supabase_schema.py"),
                 "--root", str(sql_dir), "--out", str(out_path)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue(out_path.exists(), msg="--out did not write the file")
            payload = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"],
                             "jeg111-schema-inventory-v1")


if __name__ == "__main__":
    unittest.main()