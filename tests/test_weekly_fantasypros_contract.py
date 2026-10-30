"""JEG-1268: pins the weekly FantasyPros page and row contracts (JEG-1195).

A CHECK constraint passes when its expression is NULL, not only when it is
true. So every arm has to be null-safe on its own: a row that is "unknown"
under SQL three-valued logic gets in. These tests evaluate the effective
constraint text (the last migration that defines it) under SQL three-valued
logic, with no database, so they run in CI. Set WEEKLY_FP_PG_DSN to a
throwaway local Postgres to run the same cases against a real server too;
never point it at Supabase.
"""
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "supabase/migrations"
APPLIED = MIGRATIONS / "jeg1195_weekly_fantasypros_20261029.sql"
# A proposed, unapplied follow-up lives outside supabase/migrations so nothing applies it by accident; the
# checks read it after the applied migrations, as the table would be once Jeremy approves it by name.
PROPOSED = ROOT / "docs/research/proposed-migrations"


def migration_files():
    return sorted(MIGRATIONS.glob("*.sql")) + sorted(PROPOSED.glob("*.sql"))


def migration_path(name):
    return next(path for path in migration_files() if path.name == name)


def sql_only(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def check_expression(sql, name):
    """The expression inside `constraint <name> check (...)`, or None."""
    m = None
    for m in re.finditer(r"(?is)constraint\s+%s\s+check\s*\(" % re.escape(name), sql):
        pass
    if m is None:
        return None
    depth, i = 1, m.end()
    while depth:
        depth += {"(": 1, ")": -1}.get(sql[i], 0)
        i += 1
    return sql[m.end():i - 1]


def effective_check(name):
    """The constraint as the last weekly_fantasypros migration (applied by name, then proposed) defines it."""
    found = None
    for path in migration_files():
        sql = sql_only(path.read_text(encoding="utf-8"))
        if "weekly_fantasypros" not in sql:
            continue
        expr = check_expression(sql, name)
        if expr is not None:
            found = (path.name, expr)
    return found


# --- SQL three-valued logic over the small grammar these checks use --------
TOKEN = re.compile(r"\s*(\(|\)|<>|=|'[^']*'|[A-Za-z_][A-Za-z_0-9]*|\d+)")


def tokenize(expr):
    out, pos = [], 0
    expr = expr.strip()
    while pos < len(expr):
        m = TOKEN.match(expr, pos)
        if not m:
            raise ValueError("cannot read %r" % expr[pos:pos + 20])
        out.append(m.group(1))
        pos = m.end()
    return out


def evaluate(expr, row):
    """NULL is None. Returns True, False or None (unknown)."""
    toks = tokenize(expr)
    pos = [0]

    def peek():
        return toks[pos[0]].lower() if pos[0] < len(toks) else None

    def take(expected=None):
        tok = toks[pos[0]]
        if expected and tok.lower() != expected:
            raise ValueError("expected %s, got %s" % (expected, tok))
        pos[0] += 1
        return tok

    def or_expr():
        vals = [and_expr()]
        while peek() == "or":
            take()
            vals.append(and_expr())
        if any(v is True for v in vals):
            return True
        return None if any(v is None for v in vals) else False

    def and_expr():
        vals = [not_expr()]
        while peek() == "and":
            take()
            vals.append(not_expr())
        if any(v is False for v in vals):
            return False
        return None if any(v is None for v in vals) else True

    def not_expr():
        if peek() == "not":
            take()
            v = not_expr()
            return None if v is None else not v
        return comparison()

    def comparison():
        left = primary()
        if peek() == "is":
            take()
            negate = peek() == "not"
            if negate:
                take()
            take("null")
            return (left is not None) if negate else (left is None)
        if peek() in ("=", "<>"):
            op = take()
            right = primary()
            if left is None or right is None:
                return None
            return (left == right) if op == "=" else (left != right)
        return left

    def primary():
        tok = take()
        if tok == "(":
            v = or_expr()
            take(")")
            return v
        if tok.startswith("'"):
            return tok[1:-1]
        if tok.isdigit():
            return int(tok)
        if tok.lower() == "null":
            return None
        return row[tok.lower()]

    v = or_expr()
    if pos[0] != len(toks):
        raise ValueError("unread tokens: %r" % toks[pos[0]:])
    return v


def admits(expr, row):
    """A CHECK constraint rejects a row only when the expression is false."""
    return evaluate(expr, row) is not False


SHOWN_CASES = [
    # (shown_count, total_count, rows_expected, admitted?, why)
    (None, 100, 60, False, "shown missing, total present"),
    (60, None, 60, False, "total missing, shown present"),
    (60, 100, 60, False, "showing 60 of 100: partial list"),
    (60, 60, 59, False, "one row not read"),
    (None, None, 60, True, "page shows no count line"),
    (60, 60, 60, True, "showing 60 of 60, every row read"),
]

KIND_CASES = [
    # (page_kind, ecr_rank, fpts, admitted?, why)
    ("ecr", None, None, False, "ECR rank shown as '-' lands as null and is refused"),
    ("ecr", 12, None, True, "ECR row with its rank"),
    ("ecr", 12, 14, False, "ECR row carrying FPTS"),
    ("projections", None, 14, True, "projection row"),
    ("projections", None, None, True, "projection FPTS shown as '-' stays null"),
    ("projections", 12, 14, False, "projection row carrying a rank"),
]


class EvaluatorTests(unittest.TestCase):
    def test_three_valued_logic(self):
        self.assertIsNone(evaluate("a = b", {"a": None, "b": 1}))
        self.assertIs(evaluate("a = b or a is null", {"a": None, "b": 1}), True)
        self.assertIsNone(evaluate("a = b and b = 1", {"a": None, "b": 1}))
        self.assertIs(evaluate("(a is null) = (b is null)", {"a": None, "b": 1}), False)
        self.assertIs(evaluate("not (a is null)", {"a": 1}), True)
        self.assertTrue(admits("a = b", {"a": None, "b": 1}))
        self.assertFalse(admits("a = b", {"a": 2, "b": 1}))


class PagesShownContract(unittest.TestCase):
    def setUp(self):
        found = effective_check("weekly_fantasypros_pages_shown")
        self.assertIsNotNone(found, "no migration defines weekly_fantasypros_pages_shown")
        self.source, self.expr = found

    def test_cases(self):
        for shown, total, rows, ok, why in SHOWN_CASES:
            row = {"shown_count": shown, "total_count": total, "rows_expected": rows}
            with self.subTest(why, source=self.source):
                self.assertEqual(admits(self.expr, row), ok)

    def test_no_unknown_result(self):
        # Every combination must evaluate to true or false: an unknown result
        # is how a half-null pair got past the first version.
        for shown in (None, 60, 61):
            for total in (None, 60, 61):
                for rows in (59, 60, 61):
                    row = {"shown_count": shown, "total_count": total, "rows_expected": rows}
                    with self.subTest(row=row, source=self.source):
                        self.assertIsNotNone(evaluate(self.expr, row))


class RawKindContract(unittest.TestCase):
    def setUp(self):
        found = effective_check("weekly_fantasypros_raw_kind_fields")
        self.assertIsNotNone(found)
        self.source, self.expr = found

    def test_cases(self):
        for kind, rank, fpts, ok, why in KIND_CASES:
            row = {"page_kind": kind, "ecr_rank": rank, "fpts": fpts}
            with self.subTest(why, source=self.source):
                self.assertEqual(admits(self.expr, row), ok)

    def test_no_invented_rank(self):
        # A '-' rank is never coerced to 0 or any default (JEG-1268).
        for path in migration_files():
            sql = sql_only(path.read_text(encoding="utf-8")).lower()
            if "weekly_fantasypros" not in sql:
                continue
            with self.subTest(path.name):
                self.assertNotRegex(sql, r"coalesce\s*\(\s*(?:\w+\.)?ecr_rank")
                self.assertNotRegex(sql, r"ecr_rank\s+integer[^,\n]*\bdefault\b")


class FollowUpMigration(unittest.TestCase):
    """The fix is a new migration; the applied one stays as it ran."""

    def test_follow_up_replaces_constraint_in_one_statement(self):
        found = effective_check("weekly_fantasypros_pages_shown")
        self.assertNotEqual(found[0], APPLIED.name, "the half-null fix must come from a follow-up migration")
        sql = sql_only(migration_path(found[0]).read_text(encoding="utf-8"))
        self.assertRegex(
            sql,
            r"(?is)alter\s+table\s+public\.weekly_fantasypros_pages\s+"
            r"drop\s+constraint\s+weekly_fantasypros_pages_shown\s*,\s*"
            r"add\s+constraint\s+weekly_fantasypros_pages_shown\s+check")

    def test_follow_up_marked_proposed(self):
        found = effective_check("weekly_fantasypros_pages_shown")
        header = migration_path(found[0]).read_text(encoding="utf-8").splitlines()[:6]
        self.assertTrue(any("PROPOSED" in line for line in header), header)


@unittest.skipUnless(os.environ.get("WEEKLY_FP_PG_DSN") and shutil.which("psql"),
                     "set WEEKLY_FP_PG_DSN to a throwaway local Postgres")
class RealPostgres(unittest.TestCase):
    def psql(self, sql):
        return subprocess.run(["psql", os.environ["WEEKLY_FP_PG_DSN"], "-v", "ON_ERROR_STOP=1", "-qAt", "-c", sql],
                              capture_output=True, text=True)

    def test_same_answers_as_evaluator(self):
        _, shown = effective_check("weekly_fantasypros_pages_shown")
        _, kind = effective_check("weekly_fantasypros_raw_kind_fields")
        setup = (
                 "create temp table s (shown_count int, total_count int, rows_expected int, check (%s));"
                 "create temp table k (page_kind text not null, ecr_rank int, fpts numeric, check (%s));")
        lit = lambda v: "null" if v is None else ("'%s'" % v if isinstance(v, str) else str(v))
        for shown_c, total, rows, ok, why in SHOWN_CASES:
            r = self.psql(setup % (shown, kind) + "insert into s values (%s,%s,%s);" % (lit(shown_c), lit(total), lit(rows)))
            with self.subTest(why):
                self.assertEqual(r.returncode == 0, ok, r.stderr)
        for k, rank, fpts, ok, why in KIND_CASES:
            r = self.psql(setup % (shown, kind) + "insert into k values (%s,%s,%s);" % (lit(k), lit(rank), lit(fpts)))
            with self.subTest(why):
                self.assertEqual(r.returncode == 0, ok, r.stderr)


if __name__ == "__main__":
    unittest.main()
