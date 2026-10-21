#!/usr/bin/env python3
"""Assert that tables.json classifies every relation the cloud reports (JEG-792).

Usage:
    check_classification.py tables.json inventory.txt
    check_classification.py tables.json --print-data-tables [--include-other-app]
    check_classification.py tables.json --print-no-data-tables [--include-other-app]

inventory.txt is one "schema.name" per line, as produced by export_cloud.sh from
information_schema.tables (tables and views in public, api, monitoring, ops,
ross, archive). Exits 1, naming each relation, when a relation is not in
tables.json, when tables.json has an unknown class, or when value_check_values
is marked for data. Stdlib only.
"""
import json
import sys

CLASSES = {"chain", "dashboard-other", "other-app", "skip"}
MIGRATED_SCHEMAS = ("public", "api", "monitoring", "ops")


def load(path):
    with open(path) as fh:
        doc = json.load(fh)
    rels = {r["name"]: r for r in doc["relations"]}
    bad = [n for n, r in rels.items() if r["class"] not in CLASSES]
    if bad:
        sys.exit(f"FAIL: unknown class on {bad}")
    vcv = rels.get("public.value_check_values")
    if vcv is None or vcv["migrate_data"]:
        sys.exit("FAIL: public.value_check_values must be listed with migrate_data=false")
    return rels


def data_tables(rels, include_other_app):
    out = []
    for name, r in sorted(rels.items()):
        if r["kind"] != "table" or not name.startswith(tuple(s + "." for s in MIGRATED_SCHEMAS)):
            continue
        if r["migrate_data"] or (include_other_app and r["class"] == "other-app"):
            out.append(name)
    return out


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    rels = load(argv[1])
    include_other = "--include-other-app" in argv
    if argv[2] == "--print-data-tables":
        print("\n".join(data_tables(rels, include_other)))
        return 0
    if argv[2] == "--print-no-data-tables":
        keep = set(data_tables(rels, include_other))
        names = [n for n, r in sorted(rels.items())
                 if r["kind"] == "table" and n.split(".")[0] in MIGRATED_SCHEMAS and n not in keep]
        print("\n".join(names))
        return 0
    with open(argv[2]) as fh:
        live = {line.strip() for line in fh if line.strip()}
    missing = sorted(live - set(rels))
    gone = sorted(set(rels) - live)
    if gone:
        print(f"note: {len(gone)} classified relation(s) no longer exist in the cloud: {', '.join(gone)}")
    if missing:
        print(f"FAIL: {len(missing)} relation(s) in the cloud are not classified in tables.json:")
        for n in missing:
            print(f"  {n}")
        print("Classify them in selfhost/migrate/tables.json and docs/selfhost-tables.md before exporting.")
        return 1
    print(f"ok: all {len(live)} cloud relations are classified "
          f"({len(data_tables(rels, False))} tables carry data)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
