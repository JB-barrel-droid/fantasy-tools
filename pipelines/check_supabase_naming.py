#!/usr/bin/env python3
"""Fail closed when sql/migrations/*.sql declares CREATE TABLE / VIEW / FUNCTION
names that violate the Supabase naming convention.

Convention (see docs/supabase-naming-conventions.md):

    <subproject>_<entity>

snake_case, lowercase, both halves must start with a lowercase letter, and
at least one underscore separator. A name is either conventional, on the
documented exception list, or a failure -- never silent.

The script parses the SQL directly, without a DB connection. It handles
CREATE / CREATE OR REPLACE / CREATE MATERIALIZED, the IF NOT EXISTS variant,
and schema-qualified names (``public.foo``). SQL comments are stripped before
matching, so a ``-- mentions CREATE TABLE something`` line is not flagged.

Run as part of ``make validate``. Exit 0 if every CREATE in
``sql/migrations/*.sql`` is conventional or on the exception list; exit 1
listing every violation with the source file, line, kind, and offending name.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQL_DIR = ROOT / "sql" / "migrations"

# <subproject>_<entity> -- snake_case, lowercase, both halves start with a
# letter, at least one underscore. The entity half may itself contain
# underscores (e.g. ``trade_values``).
CONVENTION_RE = re.compile(r"^[a-z][a-z0-9_]*_[a-z][a-z0-9_]*$")

# EXCEPTION LIST -- every entry needs a one-line justification in
# docs/supabase-naming-conventions.md. Adding an exception requires an edit to
# this dict AND the doc in the same change.
NAMING_EXCEPTIONS: dict[str, str] = {
    "players": (
        "Canonical identity map. The naming authority -- every other table "
        "joins to it on player_key. Every pipeline reads it; it cannot carry "
        "a subproject prefix."
    ),
}

# Match CREATE [OR REPLACE] [MATERIALIZED] (TABLE|VIEW|FUNCTION)
# [IF NOT EXISTS] [<schema>.]<name>.
# The name may be a double-quoted identifier ("my table") -- the quotes are
# stripped before the convention check, so quoted-but-unconventional names
# still fail closed. The unquoted branch also accepts a leading digit so a
# name like 2day_count_runs cannot slip past the parser (Postgres would
# require quoting it, but the validator must reject it either way).
# We anchor on the name BEFORE the function parameter list / AS clause, so a
# ``CREATE FUNCTION foo(...) RETURNS ... AS $$ ... $$`` statement still
# captures ``foo`` as the name.
CREATE_RE = re.compile(
    r"""
    CREATE\s+
    (?:OR\s+REPLACE\s+)?
    (?:MATERIALIZED\s+)?
    (?P<kind>TABLE|VIEW|FUNCTION)\s+
    (?:IF\s+NOT\s+EXISTS\s+)?
    (?:[A-Za-z_][A-Za-z0-9_]*\.)?
    (?P<name>"[^"]+"|[0-9A-Za-z_][A-Za-z0-9_]*)
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Strip SQL comments so a ``-- mentions CREATE TABLE foo`` line is not
# flagged. Order matters: block comments first, then line comments.
BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_RE = re.compile(r"--[^\n]*")


class CreateStatement(NamedTuple):
    sql_file: Path
    name: str
    kind: str
    line: int  # 1-indexed line in the cleaned (comment-stripped) text


def strip_sql_comments(sql: str) -> str:
    sql = BLOCK_COMMENT_RE.sub(" ", sql)
    sql = LINE_COMMENT_RE.sub(" ", sql)
    return sql


def iter_create_names(sql_path: Path) -> Iterable[CreateStatement]:
    raw = sql_path.read_text(encoding="utf-8")
    text = strip_sql_comments(raw)
    for match in CREATE_RE.finditer(text):
        kind = match.group("kind").upper()
        if match.group(0).upper().startswith("CREATE MATERIALIZED"):
            kind = "MATERIALIZED VIEW"
        name = match.group("name")
        # Strip double quotes from quoted identifiers ("my table" -> my table);
        # the convention check then runs on the bare name.
        if len(name) >= 2 and name.startswith('"') and name.endswith('"'):
            name = name[1:-1]
        offset = match.start()
        line = text.count("\n", 0, offset) + 1
        yield CreateStatement(
            sql_file=sql_path,
            name=name,
            kind=kind,
            line=line,
        )


def is_conventional(name: str) -> bool:
    return bool(CONVENTION_RE.match(name))


def check_sql_dir(sql_dir: Path, repo_root: Path = ROOT) -> list[str]:
    """Return a list of violations. Empty list means every CREATE is conventional
    or on the exception list."""
    if not sql_dir.exists():
        return [f"SQL directory not found: {sql_dir}"]

    sql_files = sorted(sql_dir.glob("*.sql"))
    if not sql_files:
        return [f"No *.sql files found in {sql_dir}"]

    violations: list[str] = []
    for sql_file in sql_files:
        for stmt in iter_create_names(sql_file):
            name = stmt.name
            if name in NAMING_EXCEPTIONS:
                continue
            if is_conventional(name):
                continue
            try:
                rel = sql_file.relative_to(repo_root)
            except ValueError:
                rel = sql_file
            violations.append(
                f"{rel}:{stmt.line}  {stmt.kind} {name!r} -- "
                "not on exception list and does not match "
                "<subproject>_<entity> (snake_case, lowercase, "
                "underscore-separated). See "
                "docs/supabase-naming-conventions.md."
            )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sql-dir",
        type=Path,
        default=DEFAULT_SQL_DIR,
        help="Directory of SQL migration files to scan (default: sql/migrations).",
    )
    args = parser.parse_args()

    violations = check_sql_dir(args.sql_dir)
    if not violations:
        print(
            f"OK: every CREATE in {args.sql_dir} follows "
            "<subproject>_<entity> or is on the documented exception list."
        )
        return 0

    print(
        f"NAMING CONVENTION VIOLATIONS -- {len(violations)} found in {args.sql_dir}:",
        file=sys.stderr,
    )
    for v in violations:
        print(f"  - {v}", file=sys.stderr)
    print(
        "\nEvery CREATE TABLE / VIEW / FUNCTION must be `<subproject>_<entity>` "
        "(snake_case). Genuinely shared identity tables can be added to the "
        "exception list in pipelines/check_supabase_naming.py only with a "
        "one-line justification AND a matching entry in "
        "docs/supabase-naming-conventions.md.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())