#!/usr/bin/env python3
"""JEG-111: read-only Supabase schema inventory (step 1).

This script parses the local Supabase schema sources and emits a JSON
inventory of every CREATE TABLE / CREATE VIEW / CREATE MATERIALIZED VIEW /
CREATE FUNCTION / CREATE PROCEDURE / CREATE TRIGGER it finds, grouped by
subproject (trade-value, waiver-wire, lottery/fds, razzball, cbs-ros,
shared/reference). It is read-only by construction:

  * No Supabase / DB client is imported.
  * No network call is made.
  * The only writes are the optional ``--out`` JSON file and stdout.

Scope of inputs
---------------
By default the script scans ``<repo>/sql/migrations/*.sql``. That directory
is the local schema source of truth for the live Supabase project per
``docs/supabase-source-mapping.md`` and ``docs/SUPABASE_WRITER_AUDIT.md``.
``--root`` may add additional directories (e.g. ``supabase/migrations``)
without changing the default.

Object kinds captured
---------------------
* ``TABLE`` (incl. ``CREATE TABLE IF NOT EXISTS``)
* ``VIEW`` (incl. ``CREATE OR REPLACE VIEW``)
* ``MATERIALIZED VIEW`` (incl. ``CREATE OR REPLACE MATERIALIZED VIEW``)
* ``FUNCTION`` (incl. ``CREATE OR REPLACE FUNCTION``)
* ``PROCEDURE`` (incl. ``CREATE OR REPLACE PROCEDURE``)
* ``TRIGGER`` (incl. ``CREATE CONSTRAINT TRIGGER``)

Indexes, constraints, comments, and ``ALTER TABLE`` mutations are out of
scope - the task is a TABLE / VIEW / FUNCTION inventory. Statements that
the script does not classify land in ``unclassified`` so the reviewer can
resolve them; the script never guesses a subproject.

Grouping heuristic
------------------
Subproject assignment combines filename hints and object-name prefixes,
in that order:

1. ``pipeline_write_audit`` in filename or object name -> ``shared/reference``
2. ``cbs_ros`` / ``cbs-ros`` in filename or object name -> ``cbs-ros``
3. ``razzball`` in filename or object name -> ``razzball``
4. ``lottery`` / ``fds`` in filename or object name -> ``lottery/fds``
5. ``waiver`` / ``vorp`` / ``roster_assumption`` / ``publisher_vorp`` /
   ``publisher_translated_values`` in filename or object name ->
   ``waiver-wire``
6. ``source_trade_values`` / ``source_value_adjustments`` /
   ``trade_value`` in filename or object name -> ``trade-value``
7. Otherwise -> ``unclassified`` (never a guess)

Both schema-qualified (``public.foo``) and unqualified (``foo``) names are
handled; only the unqualified base name is grouped.

Output
------
JSON object::

    {
      "schema_version": "jeg111-schema-inventory-v1",
      "roots": ["sql/migrations"],
      "generated_at_utc": "2026-10-02T20:21:07Z",
      "totals": {"TABLE": N, "VIEW": ..., ..., "files": N},
      "by_subproject": {
        "trade-value":   {"TABLE": [{"name": ..., "schema": ..., "file": ..., "qualified_name": ...}, ...], ...},
        ...
        "unclassified":  {...}
      },
      "files": [
        {"path": "sql/migrations/001_...sql", "object_kinds": ["TABLE"], "object_names": ["public.foo"]}
      ]
    }

CLI
--
``python3 pipelines/inventory_supabase_schema.py --out /tmp/inv.json``
Emits JSON to stdout and, if ``--out`` is given, also to that path. The
default root is ``sql/migrations`` relative to the repo (the directory two
levels up from this script). Pass ``--root PATH`` one or more times to
override the default.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "jeg111-schema-inventory-v1"

# Recognised object kinds and the regex used to extract (schema, name).
# Names are captured greedily up to the terminator that follows them:
#   TABLE     -> whitespace + '('
#   VIEW      -> whitespace + ' AS' / ';' / whitespace (matview / or replace)
#   FUNCTION  -> whitespace + '('
#   TRIGGER   -> whitespace + ' ON' / ';' / whitespace
# Schemas (e.g. 'public.') are stripped into a separate field.
_KIND_PATTERNS: list = [
    (
        "TABLE",
        r"CREATE\s+(?:GLOBAL\s+(?:TEMPORARY|TEMP)\s+)?TABLE"
        r"(?:\s+IF\s+NOT\s+EXISTS)?"
        r"\s+(?:(?P<s1>[\w]+)\.)?(?P<n1>[\w]+)\s*\(",
    ),
    (
        "VIEW",
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW"
        r"(?:\s+IF\s+NOT\s+EXISTS)?"
        r"\s+(?:(?P<s2>[\w]+)\.)?(?P<n2>[\w]+)",
    ),
    (
        "FUNCTION",
        r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION"
        r"\s+(?:(?P<s3>[\w]+)\.)?(?P<n3>[\w]+)\s*\(",
    ),
    (
        "PROCEDURE",
        r"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE"
        r"\s+(?:(?P<s4>[\w]+)\.)?(?P<n4>[\w]+)\s*\(",
    ),
    (
        "TRIGGER",
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:CONSTRAINT\s+)?TRIGGER"
        r"\s+(?P<n5>[\w]+)",
    ),
]
_COMPILED = [(kind, re.compile(pattern, re.IGNORECASE | re.DOTALL))
             for kind, pattern in _KIND_PATTERNS]

# Subproject rules. Order matters: first match wins. A rule is
# (subproject, [substring tests...]). Each substring test is applied to the
# lower-cased filename (without directory) and the lower-cased object name;
# if any substring matches either, the subproject is assigned.
# Subprojects here MUST stay aligned with the inventory output contract
# documented at the top of this file.
SUBPROJECT_RULES: list = [
    ("shared/reference", ("pipeline_write_audit",)),
    ("cbs-ros", ("cbs_ros", "cbs-ros")),
    ("razzball", ("razzball",)),
    ("lottery/fds", ("lottery", "fds_")),
    (
        "waiver-wire",
        (
            "waiver",
            "vorp",
            "roster_assumption",
            "publisher_vorp",
            "publisher_translated",
        ),
    ),
    (
        "trade-value",
        ("source_trade_values", "source_value_adjustments", "trade_value"),
    ),
]


def _strip_comments_and_strings(sql: str) -> str:
    """Return ``sql`` with comments and string contents blanked out.

    Token-level stripping is required so that ``CREATE`` keywords inside
    string literals or ``$$ ... $$`` dollar-quoted PL/pgSQL bodies cannot
    leak into the parser. The output is the same length as the input
    (whitespace-only replacements) so byte offsets remain useful.
    """

    out: list = []
    i = 0
    n = len(sql)
    state = "code"  # code | line_comment | block_comment | sq | dq | dollar
    dollar_tag = None
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "-" and nxt == "-":
                state = "line_comment"
                out.append("  ")
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                # Standard single-quoted string: doubled '' is an escaped
                # single quote inside the string.
                state = "sq"
                out.append(" ")
                i += 1
                continue
            if ch == '"':
                # Double-quoted identifier; same scan rules apply.
                state = "dq"
                out.append(" ")
                i += 1
                continue
            if ch == "$":
                # Dollar-quoted string: $tag$...$tag$ or $$...$$.
                m = re.match(r"\$([A-Za-z_][\w]*)?\$", sql[i:])
                if m:
                    dollar_tag = m.group(0)
                    state = "dollar"
                    out.append(" " * len(m.group(0)))
                    i += len(m.group(0))
                    continue
            out.append(ch)
            i += 1
            continue
        if state == "line_comment":
            if ch == "\n":
                state = "code"
                out.append("\n")
            else:
                out.append(" ")
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                out.append("  ")
                i += 2
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if state == "sq":
            if ch == "'" and nxt == "'":
                out.append("  ")
                i += 2
                continue
            if ch == "'":
                state = "code"
                out.append(" ")
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if state == "dq":
            if ch == '"' and nxt == '"':
                out.append("  ")
                i += 2
                continue
            if ch == '"':
                state = "code"
                out.append(" ")
                i += 1
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        if state == "dollar":
            if sql[i:i + len(dollar_tag or "")] == dollar_tag:
                out.append(" " * len(dollar_tag or ""))
                i += len(dollar_tag or "")
                state = "code"
                dollar_tag = None
                continue
            out.append("\n" if ch == "\n" else " ")
            i += 1
            continue
        # Defensive: should not reach here.
        i += 1
    return "".join(out)


def _extract_objects(clean_sql: str) -> list:
    """Return a list of (kind, schema_name_or_None, base_name) tuples.

    Matches are returned in file order. Each regex is anchored on its own
    CREATE keyword, so they do not overlap on real statements. Each regex
    is applied against the *cleaned* SQL where comments and string bodies
    have been blanked.
    """

    found: list = []
    for kind, pattern in _COMPILED:
        for m in pattern.finditer(clean_sql):
            gd = m.groupdict()
            schema = None
            name = None
            for prefix in ("s1", "s2", "s3", "s4"):
                gschema = gd.get(prefix)
                if gschema:
                    schema = gschema.lower()
                    break
            for prefix in ("n1", "n2", "n3", "n4", "n5"):
                gname = gd.get(prefix)
                if gname:
                    name = gname
                    break
            if name is None:
                continue
            found.append((kind, schema, name))
    return found


def _classify(filename: str, object_name: str) -> str:
    """Return the subproject for a filename + object-name pair.

    See module docstring for the heuristic order. ``filename`` is the
    base filename (no directory); ``object_name`` is the unqualified
    base name (no schema). The function never raises; anything that
    does not match a rule lands in ``"unclassified"``.
    """

    haystack = (filename.lower() + " " + object_name.lower())
    for subproject, needles in SUBPROJECT_RULES:
        for needle in needles:
            if needle in haystack:
                return subproject
    return "unclassified"


def _inventory_file(path: Path) -> dict:
    """Return the per-file inventory row for ``path``.

    The returned dict carries the file path, the kinds declared, and the
    full object list (each as a small dict with kind/schema/name). The
    caller uses this for both the per-file table and the by-subproject
    aggregation.
    """

    raw = path.read_text(encoding="utf-8", errors="replace")
    clean = _strip_comments_and_strings(raw)
    objects: list = []
    for kind, schema, name in _extract_objects(clean):
        objects.append({
            "kind": kind,
            "schema": schema,
            "name": name,
            "qualified_name": f"{schema}.{name}" if schema else name,
        })
    return {
        "path": str(path),
        "object_kinds": sorted({o["kind"] for o in objects}),
        "objects": objects,
    }


def build_inventory(roots: list) -> dict:
    """Walk every root, collect objects, and assemble the inventory dict."""

    files: list = []
    for root in roots:
        if not root.exists():
            # Skip silently: --root is opt-in and the default may not be
            # present in a slim checkout. The reviewer can pass an
            # explicit path when running outside the repo.
            continue
        for path in sorted(root.rglob("*.sql")):
            files.append(_inventory_file(path))

    by_subproject: dict = {}
    for file_row in files:
        for obj in file_row["objects"]:
            filename = Path(file_row["path"]).name
            sub = _classify(filename, obj["name"])
            by_subproject.setdefault(sub, []).append({
                "kind": obj["kind"],
                "schema": obj["schema"],
                "name": obj["name"],
                "qualified_name": obj["qualified_name"],
                "file": file_row["path"],
            })

    totals_kinds: dict = {}
    for items in by_subproject.values():
        for it in items:
            totals_kinds[it["kind"]] = totals_kinds.get(it["kind"], 0) + 1

    file_rows = [
        {
            "path": f["path"],
            "object_kinds": f["object_kinds"],
            "object_names": [o["qualified_name"] for o in f["objects"]],
        }
        for f in files
    ]

    return {
        "schema_version": SCHEMA_VERSION,
        "roots": [str(r) for r in roots],
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "totals": {
            **totals_kinds,
            "files": len(files),
            "subprojects": len(by_subproject),
        },
        "by_subproject": {
            sub: sorted(items, key=lambda x: (x["kind"], x["qualified_name"]))
            for sub, items in sorted(by_subproject.items())
        },
        "files": file_rows,
    }


def _default_root() -> Path:
    """Return ``<repo>/sql/migrations``, where the repo root is the parent
    of this script's ``pipelines/`` directory."""

    return Path(__file__).resolve().parents[1] / "sql" / "migrations"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Supabase schema inventory (JEG-111)."
    )
    parser.add_argument(
        "--root",
        action="append",
        default=None,
        help="Directory of *.sql files (may be repeated). "
             "Defaults to <repo>/sql/migrations.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional path to write the JSON inventory to, in addition to "
             "stdout.",
    )
    args = parser.parse_args(argv)

    roots = [Path(r) for r in (args.root or [str(_default_root())])]
    inventory = build_inventory(roots)

    payload = json.dumps(inventory, indent=2, sort_keys=False)
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()
    if args.out:
        Path(args.out).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())