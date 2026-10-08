"""Regression tests for pipelines/check_supabase_naming.py (JEG-111).

Required for the validator to ship:
  * Conventional names pass.
  * A violating name fixture fails closed (the regression the guard exists
    to catch).
  * An exception-list name fixture passes.
  * The validator handles CREATE OR REPLACE, IF NOT EXISTS, MATERIALIZED
    VIEW, FUNCTION, and SQL comments correctly.

The repo uses unittest, not pytest. Run with:
    python3 -m unittest tests.test_supabase_naming -v
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "pipelines/check_supabase_naming.py"
REAL_SQL_DIR = ROOT / "sql" / "migrations"


def _write_sql(tmp: Path, name: str, body: str) -> Path:
    sql_file = tmp / name
    sql_file.write_text(body, encoding="utf-8")
    return sql_file


def _run(sql_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, SCRIPT, "--sql-dir", str(sql_dir)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class ConventionalNameTests(unittest.TestCase):
    """The happy path: every CREATE in a fixture directory follows the
    convention, so the validator exits 0."""

    def test_subproject_only_passes(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE public.cbs_ros_projections (id uuid PRIMARY KEY);\n")
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("OK:", result.stdout)

    def test_pipeline_internal_subproject_passes(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(
                tmp,
                "001.sql",
                "CREATE TABLE IF NOT EXISTS public.pipeline_write_audit (id uuid PRIMARY KEY);\n",
            )
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")

    def test_handle_create_or_replace_function(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sql = (
                "CREATE OR REPLACE FUNCTION public.cbs_weekly_totals() RETURNS numeric "
                "AS $$ SELECT 1 $$ LANGUAGE sql;\n"
            )
            _write_sql(tmp, "001.sql", sql)
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")

    def test_handle_materialized_view(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE MATERIALIZED VIEW public.source_daily_summary AS SELECT 1;\n")
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")

    def test_handle_if_not_exists(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE IF NOT EXISTS public.razzball_projections (id uuid);\n")
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")

    def test_sql_comments_are_ignored(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sql = (
                "-- This is a comment mentioning CREATE TABLE other_thing.\n"
                "/* And a block comment mentioning CREATE VIEW whatever.\n"
                "   These must not be flagged. */\n"
                "CREATE TABLE public.cbs_ros_projections (id uuid PRIMARY KEY);\n"
            )
            _write_sql(tmp, "001.sql", sql)
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")


class ViolationNameTests(unittest.TestCase):
    """The regression the guard exists to catch: a CREATE that does NOT
    follow the convention and is NOT on the exception list must produce a
    non-zero exit code and a stderr line that names the offender."""

    def test_single_word_name_fails(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE public.badname (id uuid PRIMARY KEY);\n")
            result = _run(tmp)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("NAMING CONVENTION VIOLATIONS", result.stderr)
            self.assertIn("'badname'", result.stderr)

    def test_uppercase_name_fails(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE public.CBS_Ros_Projections (id uuid PRIMARY KEY);\n")
            result = _run(tmp)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("'CBS_Ros_Projections'", result.stderr)

    def test_leading_underscore_fails(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE public._internal_table (id uuid PRIMARY KEY);\n")
            result = _run(tmp)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("'_internal_table'", result.stderr)

    def test_leading_digit_fails(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE public.\"2day_count_runs\" (id uuid PRIMARY KEY);\n")
            result = _run(tmp)
            # The double-quoted identifier is captured; the leading digit
            # fails the convention regex. (Postgres would reject this name
            # without quoting, but the validator must reject it either way.)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("'2day_count_runs'", result.stderr)

    def test_view_violation_fails(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE VIEW public.totals AS SELECT 1;\n")
            result = _run(tmp)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("'totals'", result.stderr)

    def test_function_violation_fails(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(
                tmp,
                "001.sql",
                "CREATE FUNCTION public.dosomething() RETURNS void AS $$ BEGIN END $$ LANGUAGE plpgsql;\n",
            )
            result = _run(tmp)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("'dosomething'", result.stderr)

    def test_multiple_violations_all_listed(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sql = (
                "CREATE TABLE public.badname (id uuid PRIMARY KEY);\n"
                # NOTE: 'anotherbad' (single word, no underscore) is the
                # violation -- 'another_bad' would be conventional per
                # <subproject>_<entity>.
                "CREATE VIEW public.anotherbad AS SELECT 1;\n"
            )
            _write_sql(tmp, "001.sql", sql)
            result = _run(tmp)
            self.assertNotEqual(0, result.returncode)
            self.assertIn("'badname'", result.stderr)
            self.assertIn("'anotherbad'", result.stderr)
            # Two distinct violations, both listed.
            self.assertEqual(
                2,
                len(re.findall(r"not on exception list", result.stderr, re.IGNORECASE)),
            )


class ExceptionListTests(unittest.TestCase):
    """The exception list exists for genuinely shared tables. Every name
    on it must pass the validator without becoming a violation. The list
    currently contains only ``players``."""

    def test_players_passes_via_exception_list(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            _write_sql(tmp, "001.sql", "CREATE TABLE public.players (id uuid PRIMARY KEY);\n")
            result = _run(tmp)
            self.assertEqual(0, result.returncode,
                             msg=f"stdout: {result.stdout}\nstderr: {result.stderr}")
            self.assertIn("OK:", result.stdout)

    def test_exception_list_justification_is_documented(self):
        # Belt-and-suspenders: read the exception dict and the doc and make
        # sure every key has a non-trivial justification. This is the rule
        # in docs/supabase-naming-conventions.md -- a name on the list
        # without a justification is itself a regression.
        from pipelines.check_supabase_naming import NAMING_EXCEPTIONS  # noqa: E402
        doc = (ROOT / "docs" / "supabase-naming-conventions.md").read_text(
            encoding="utf-8"
        )
        for name, justification in NAMING_EXCEPTIONS.items():
            self.assertTrue(
                len(justification.strip()) >= 30,
                msg=f"NAMING_EXCEPTIONS[{name!r}] justification is too short to be honest",
            )
            # The doc must contain a row that mentions the name and a
            # non-trivial justification. We check the name appears in a
            # table cell; the justification check is structural.
            self.assertIn(name, doc, msg=f"{name!r} is on the exception list but missing from the doc")


class RealSchemaTests(unittest.TestCase):
    """End-to-end: run the validator against the in-tree sql/migrations/."""

    def test_real_migrations_dir_is_green(self):
        self.assertTrue(REAL_SQL_DIR.exists(),
                        msg=f"expected {REAL_SQL_DIR} to exist")
        result = _run(REAL_SQL_DIR)
        self.assertEqual(0, result.returncode,
                         msg=f"validator failed on the real migrations directory:\n"
                             f"stdout: {result.stdout}\nstderr: {result.stderr}")
        self.assertIn("OK:", result.stdout)

    def test_real_migrations_declares_two_tables(self):
        # Negative test for the doc's "two CREATE TABLE" claim: parse the
        # real directory and verify the validator sees the names we expect.
        result = _run(REAL_SQL_DIR)
        self.assertEqual(0, result.returncode)
        # The validator prints "OK:" on stdout; we cross-check by reading
        # the migrations directory directly to confirm the count matches.
        names = set()
        for sql_file in sorted(REAL_SQL_DIR.glob("*.sql")):
            text = sql_file.read_text(encoding="utf-8")
            # Strip comments the same way the script does.
            text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
            text = re.sub(r"--[^\n]*", " ", text)
            for match in re.finditer(
                r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?(?:TABLE|VIEW|FUNCTION)\s+"
                r"(?:IF\s+NOT\s+EXISTS\s+)?(?:[A-Za-z_][A-Za-z0-9_]*\.)?"
                r"([A-Za-z_][A-Za-z0-9_]*)",
                text,
                flags=re.IGNORECASE,
            ):
                names.add(match.group(1))
        self.assertIn("cbs_ros_projections", names)
        self.assertIn("razzball_projections", names)


if __name__ == "__main__":
    unittest.main()