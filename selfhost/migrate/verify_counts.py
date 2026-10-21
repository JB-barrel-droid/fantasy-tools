#!/usr/bin/env python3
"""Compare per-table row counts in the local Postgres with the cloud export (JEG-792).

    verify_counts.py --counts OUT/counts.tsv [--tables-json tables.json]
                     [--database-url-env LOCAL_DATABASE_URL]

counts.tsv is "schema.table<TAB>count" per line, written by export_cloud.sh
(or export_via_rest.py) from exact count(*) at export time. The local counts
are read with psql (stdlib only, no driver). Exits 1 and prints every
mismatch, every table missing locally, and, when tables.json is given, every
structure-only table that unexpectedly has rows (value_check_values must be
empty). The connection string is read from the environment, never printed.
"""
import argparse
import json
import os
import re
import subprocess
import sys

NAME = re.compile(r"^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*$")


def psql(url, sql):
    r = subprocess.run(["psql", url, "-X", "-v", "ON_ERROR_STOP=1", "-At", "-F", "\t", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:500])
    return [line.split("\t") for line in r.stdout.splitlines() if line]


def count_query(names):
    parts = []
    for n in names:
        if not NAME.match(n):
            raise ValueError(f"unexpected table name {n!r}")
        s, t = n.split(".")
        parts.append(f"select '{n}', count(*) from \"{s}\".\"{t}\"")
    return " union all ".join(parts)


def existing(url, names):
    rows = psql(url, "select n.nspname||'.'||c.relname from pg_class c join pg_namespace n "
                     "on n.oid=c.relnamespace where c.relkind in ('r','p')")
    have = {r[0] for r in rows}
    return [n for n in names if n in have], [n for n in names if n not in have]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--counts", required=True)
    ap.add_argument("--tables-json")
    ap.add_argument("--database-url-env", default="LOCAL_DATABASE_URL")
    a = ap.parse_args()
    url = os.environ.get(a.database_url_env, "")
    if not url:
        sys.exit(f"FAIL: ${a.database_url_env} is not set")

    expected = {}
    with open(a.counts) as fh:
        for line in fh:
            if line.strip():
                name, n = line.rstrip("\n").split("\t")
                expected[name] = int(n)
    if not expected:
        sys.exit("FAIL: counts file is empty")

    problems = []
    present, absent = existing(url, sorted(expected))
    problems += [f"MISSING  {n}: table not found locally (cloud {expected[n]})" for n in absent]
    local = {r[0]: int(r[1]) for r in psql(url, count_query(present))} if present else {}

    for n in present:
        status = "ok" if local[n] == expected[n] else "MISMATCH"
        print(f"{status:8} {n:50} cloud {expected[n]:>9}  local {local[n]:>9}")
        if status != "ok":
            problems.append(f"MISMATCH {n}: cloud {expected[n]}, local {local[n]}")

    if a.tables_json:
        with open(a.tables_json) as fh:
            rels = json.load(fh)["relations"]
        nodata = [r["name"] for r in rels if r["kind"] == "table" and r["migrate_structure"]
                  and r["name"] not in expected]
        p2, a2 = existing(url, nodata)
        if "public.value_check_values" in a2:
            problems.append("MISSING  public.value_check_values: its empty structure must exist")
        for n, c in ((r[0], int(r[1])) for r in (psql(url, count_query(p2)) if p2 else [])):
            if c:
                problems.append(f"UNEXPECTED {n}: structure-only table has {c} rows")

    if problems:
        print("\nverify_counts: FAIL")
        for p in problems:
            print("  " + p)
        return 1
    print(f"\nverify_counts: OK, {len(present)} tables match the cloud export exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
