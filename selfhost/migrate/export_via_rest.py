#!/usr/bin/env python3
"""FALLBACK cloud export over PostgREST, for when a direct Postgres connection
to the restricted cloud project is refused (JEG-792, lane B).

    *************************************************************************
    WARNING: this reads every migrated row through https://<ref>.supabase.co
    /rest/v1 as JSON. JSON over REST is several times larger than pg_dump's
    compressed format, and ALL of it counts as egress on a project that is
    already over its quota. The API may itself answer HTTP 402 (quota) at any
    page; the script then stops and says so. Prefer export_cloud.sh.
    It also exports DATA ONLY: the structure (tables, views, functions,
    policies) must come from `pg_dump --schema-only` (a few hundred kB) or,
    failing that, be rebuilt from supabase/migrations + sql/migrations, which
    is NOT verified to match the cloud.
    *************************************************************************

Usage:
    export SUPABASE_URL=https://iskiybsimubiujwuchsl.supabase.co
    export SUPABASE_SERVICE_KEY=...        # service_role key; never printed
    selfhost/migrate/export_via_rest.py --out OUT_DIR --yes-i-accept-egress
        [--tables public.bakes,public.players]   # default: all data tables in tables.json
        [--page 1000]

Writes OUT_DIR/rest/<schema>.<table>.jsonl (one JSON object per line),
OUT_DIR/counts.tsv (exact counts from Content-Range, the same format
export_cloud.sh writes, so verify_counts.py works unchanged) and
OUT_DIR/load_rest.sql (psql script: \\copy each file into a temp table and
insert with jsonb_populate_record into the already-created structure).

Schemas other than public must be exposed by PostgREST (api usually is;
monitoring usually is not). A table PostgREST will not serve is reported and
the run ends with exit 1, so nothing is silently missing. Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
WARNING = __doc__.split("Usage:")[0]


class Quota(Exception):
    pass


def env(name):
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"FAIL: {name} is not set")
    return v


def request(base, key, path, schema, headers=None, method="GET"):
    req = urllib.request.Request(base + path, method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Accept-Profile", schema)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        return resp.headers, resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        if e.code == 402:
            raise Quota(f"HTTP 402 on {path.split('?')[0]}: {body}")
        raise RuntimeError(f"HTTP {e.code} on {path.split('?')[0]}: {body}")


def primary_keys(base, key, schema):
    """Primary-key columns per table from PostgREST's OpenAPI (<pk/> markers)."""
    _, raw = request(base, key, "/rest/v1/", schema, {"Accept": "application/openapi+json"})
    spec = json.loads(raw)
    out = {}
    for table, d in (spec.get("definitions") or {}).items():
        props = d.get("properties") or {}
        out[table] = ([c for c, p in props.items() if "<pk/>" in (p.get("description") or "")],
                      list(props))
    return out


def exact_count(base, key, schema, table):
    h, _ = request(base, key, f"/rest/v1/{table}?select=*", schema,
                   {"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"}, method="HEAD")
    m = re.search(r"/(\d+)$", h.get("Content-Range", ""))
    if not m:
        raise RuntimeError(f"no exact count for {schema}.{table} (Content-Range {h.get('Content-Range')!r})")
    return int(m.group(1))


def main():
    ap = argparse.ArgumentParser(description="Fallback REST export (costs egress).")
    ap.add_argument("--out", required=True)
    ap.add_argument("--tables", help="comma-separated schema.table list")
    ap.add_argument("--page", type=int, default=1000)
    ap.add_argument("--yes-i-accept-egress", action="store_true")
    a = ap.parse_args()

    print(WARNING, file=sys.stderr)
    if not a.yes_i_accept_egress:
        sys.exit("Refusing to run without --yes-i-accept-egress (read the warning above).")

    base = env("SUPABASE_URL").rstrip("/")
    key = env("SUPABASE_SERVICE_KEY")
    if a.tables:
        tables = [t.strip() for t in a.tables.split(",") if t.strip()]
    else:
        with open(os.path.join(HERE, "tables.json")) as fh:
            rels = json.load(fh)["relations"]
        tables = sorted(r["name"] for r in rels if r["migrate_data"])
    if "public.value_check_values" in tables:
        sys.exit("FAIL: value_check_values is never exported")

    out_rest = os.path.join(a.out, "rest")
    os.makedirs(out_rest, exist_ok=True)
    os.chmod(a.out, 0o700)

    pks, counts, failed, loads = {}, {}, [], []
    try:
        for name in tables:
            schema, table = name.split(".")
            if schema not in pks:
                try:
                    pks[schema] = primary_keys(base, key, schema)
                except RuntimeError as e:
                    pks[schema] = {}
                    print(f"  {schema}: schema not served by PostgREST ({e})", file=sys.stderr)
            if table not in pks[schema]:
                failed.append(f"{name}: not exposed by PostgREST")
                continue
            pk, cols = pks[schema][table]
            order = ",".join(f"{c}.asc" for c in (pk or cols))
            total = exact_count(base, key, schema, table)
            path = os.path.join(out_rest, f"{name}.jsonl")
            got = 0
            with open(path, "w") as fh:
                while got < total:
                    q = urllib.parse.urlencode({"select": "*", "order": order,
                                                "limit": a.page, "offset": got})
                    _, raw = request(base, key, f"/rest/v1/{table}?{q}", schema)
                    page = json.loads(raw)
                    if not page:
                        break
                    for row in page:
                        fh.write(json.dumps(row, separators=(",", ":")) + "\n")
                    got += len(page)
            print(f"  {name:50} {got:>9} rows" + ("" if pk else "  (no PK: ordered by all columns)"))
            if got != total:
                failed.append(f"{name}: read {got} rows, Content-Range said {total}")
            counts[name] = total
            loads.append((name, path))
    except Quota as e:
        print(f"\nSTOPPED: {e}\nThe project is over its egress quota; the REST path is blocked too.",
              file=sys.stderr)
        return 2

    with open(os.path.join(a.out, "counts.tsv"), "w") as fh:
        for n in sorted(counts):
            fh.write(f"{n}\t{counts[n]}\n")
    with open(os.path.join(a.out, "load_rest.sql"), "w") as fh:
        fh.write("-- Generated by export_via_rest.py. Run into a database that already has the\n"
                 "-- structure (pg_restore --schema-only), with triggers deferred by load order.\n"
                 "\\set ON_ERROR_STOP on\nbegin;\nset local session_replication_role = replica;\n"
                 "create temp table _rest_rows (j jsonb) on commit drop;\n")
        for name, path in loads:
            schema, table = name.split(".")
            fh.write(f"truncate _rest_rows;\n"
                     f"\\copy _rest_rows (j) from '{os.path.abspath(path)}' "
                     f"with (format csv, quote e'\\x01', delimiter e'\\x02')\n"
                     f"insert into \"{schema}\".\"{table}\" select (jsonb_populate_record("
                     f"null::\"{schema}\".\"{table}\", j)).* from _rest_rows;\n")
        fh.write("-- Sequence values are not in a schema-only restore: move each owned\n"
                 "-- sequence past the max of its column.\n"
                 "do $seq$ declare r record; m bigint; begin\n"
                 "  for r in select s.oid::regclass seq, a.attrelid::regclass tbl, a.attname col\n"
                 "    from pg_class s join pg_depend d on d.objid = s.oid and d.deptype in ('a','i')\n"
                 "    join pg_attribute a on a.attrelid = d.refobjid and a.attnum = d.refobjsubid\n"
                 "    join pg_namespace n on n.oid = s.relnamespace\n"
                 "    where s.relkind = 'S' and n.nspname in ('public','api','monitoring','ops') loop\n"
                 "    execute format('select max(%I)::bigint from %s', r.col, r.tbl) into m;\n"
                 "    if m is not null then perform setval(r.seq, m); end if;\n"
                 "  end loop; end $seq$;\n")
        fh.write("commit;\n")

    if failed:
        print("\nexport_via_rest: INCOMPLETE")
        for f in failed:
            print("  " + f)
        return 1
    print(f"\nexport_via_rest: OK, {len(counts)} tables. Load with psql -f {a.out}/load_rest.sql, "
          f"then verify_counts.py --counts {a.out}/counts.tsv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
