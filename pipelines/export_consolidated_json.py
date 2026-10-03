#!/usr/bin/env python3
"""Export the consolidation layer to JSON for the static site (JEG-324).

Reads rows from public.consolidated_values (Supabase) — or accepts rows
directly from build_consolidated_values.py — and emits the served artifact
`consolidated-values.json` with filters and ease-of-use features:

  * `weeks_available`: sorted list of {season, week} with data
  * `sources_available`: per (season, week), the sources that priced it
  * `index`: pre-built nested lookup {player: {source: {week: {combo: value}}}}
    for O(1) reads without scanning the row array
  * `rows`: the flat row array (canonical data)

Usage:
  # From Supabase (table must exist; see sql/consolidated_values.sql):
  python3 pipelines/export_consolidated_json.py --out output/consolidated-values.json

  # From an in-memory row list (used by build_consolidated_values.py):
  from export_consolidated_json import build_export_doc
  doc = build_export_doc(rows, detail_sha256)
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def build_export_doc(rows, detail_sha256, vintages=None, bake_id=None):
    """Build the JSON export document from consolidation rows."""
    # weeks_available: sorted unique (season, week)
    weeks = sorted({(r["season"], r["week"]) for r in rows})
    weeks_available = [{"season": s, "week": w} for s, w in weeks]

    # sources_available: per (season, week) -> sorted source list
    per_week_sources = {}
    for r in rows:
        key = (r["season"], r["week"])
        per_week_sources.setdefault(key, set()).add(r["source"])
    sources_available = [
        {"season": s, "week": w, "sources": sorted(per_week_sources[(s, w)])}
        for s, w in weeks
    ]

    # index: player -> source -> "season-week" -> "scoring_teams[_qb]_view" -> value
    index = {}
    for r in rows:
        combo = f"{r['scoring']}_{r['teams']}"
        if r["qb_variant"]:
            combo += f"_{r['qb_variant']}"
        combo += f"__{r['view']}"
        wk = f"{r['season']}-w{r['week']}"
        index.setdefault(r["player"], {}).setdefault(r["source"], {}).setdefault(wk, {})[combo] = r["value"]

    # bake_id: prefer explicit, else most common row bake_id
    if bake_id is None:
        bake_ids = {}
        for r in rows:
            bake_ids[r["bake_id"]] = bake_ids.get(r["bake_id"], 0) + 1
        bake_id = max(bake_ids, key=bake_ids.get) if bake_ids else "unknown"

    return {
        "schema": "consolidated-values-v1",
        "bake_id": bake_id,
        "detail_sha256": detail_sha256,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks_available": weeks_available,
        "sources_available": sources_available,
        "vintages": vintages or {},
        "index": index,
        "rows": rows,
    }


def fetch_rows_from_supabase():
    """Fetch all consolidation rows from Supabase (paginated)."""
    from pathlib import Path as _P
    skill_bin = _P.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"
    sys.path.insert(0, str(skill_bin))
    import sbclient

    rows = []
    offset = 0
    batch = 1000
    while True:
        chunk = sbclient.get(
            "consolidated_values",
            f"?select=*&order=season,week,source,player&limit={batch}&offset={offset}",
        )
        if not chunk:
            break
        rows.extend(chunk)
        offset += batch
        if len(chunk) < batch:
            break
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="Output JSON path")
    ap.add_argument("--detail-sha256", default="",
                    help="SHA256 of the detail fixture (for the export header)")
    ap.add_argument("--minify", action="store_true",
                    help="Minified output (for dist/)")
    args = ap.parse_args()

    rows = fetch_rows_from_supabase()
    print(f"Fetched {len(rows)} rows from public.consolidated_values")
    if not rows:
        print("ERROR: no rows fetched; is the table populated?", file=sys.stderr)
        sys.exit(1)

    doc = build_export_doc(rows, args.detail_sha256 or "unknown")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        if args.minify:
            json.dump(doc, f, separators=(",", ":"))
        else:
            json.dump(doc, f, indent=1)
    print(f"Wrote {out} ({out.stat().st_size} bytes, "
          f"{len(doc['weeks_available'])} weeks)")


if __name__ == "__main__":
    main()
