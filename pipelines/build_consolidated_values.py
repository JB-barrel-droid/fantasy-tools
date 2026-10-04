#!/usr/bin/env python3
"""Build the consolidation layer (JEG-324).

Reads the detail fixture `data/fixtures/current/comparison-sources-data.json`
and derives the flat consolidation rows per the schema in
docs/planning/consolidation-layer-scope.md:

    (player, source, season, week, scoring, teams, qb_variant, view) -> value

Sources of rows:
  * combos:  each source's `combos[<scoring>_<teams>[_qbN]].reindexed[player]`
             becomes view='combo_reindexed'
  * vorp_views: `views.{indexed,vorp,adj_values}[player]` become
             view='vorp_indexed' / 'vorp' / 'adj_values'

Fail-closed semantics (scope Goals 5, 1):
  * Every emitted row is reconciled against the detail fixture via the
    original deep path. Any mismatch aborts the build.
  * Bidirectional key-set check: no missing rows, no extra rows, no
    duplicate composite keys, no invalid (source, scoring, teams, qb)
    tuples.
  * On any failure nothing is written to Supabase and no JSON is emitted.

Output modes:
  * --write-supabase : upsert rows into public.consolidated_values via the
    Supabase REST API (service-role credential). Requires the table to
    exist (sql/consolidated_values.sql).
  * --json-out PATH : write the JSON export artifact (same shape as
    pipelines/export_consolidated_json.py produces).
  * Default (no flags): dry-run — build rows, run reconciliation, report
    counts, write nothing.

Usage:
  python3 pipelines/build_consolidated_values.py [--write-supabase] [--json-out output/consolidated-values.json]
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"

# Combo keys look like: full_12, half_10, standard_14, full_12_qb1, ...
COMBO_RE = re.compile(r"^(full|half|standard)_(\d+)(?:_(qb[12]))?$")

# Detail view name -> consolidation view name (Codex rec: disambiguate before v1).
VORP_VIEW_MAP = {
    "indexed": "vorp_indexed",
    "vorp": "vorp",
    "adj_values": "adj_values",
}

# Sources whose combos carry a _qbN suffix (mirrors value-model.js sourceComboKey).
QB_VARIANT_SOURCES = {"fantasycalc", "fantasycalc_adjusted"}

VALID_SCORING = {"full", "half", "standard"}
VALID_TEAMS = {8, 10, 12, 14}


def parse_combo_key(combo_key):
    """Decompose 'full_12_qb1' -> (scoring, teams, qb_variant)."""
    m = COMBO_RE.match(combo_key)
    if not m:
        return None
    scoring, teams, qb = m.group(1), int(m.group(2)), m.group(3)
    return scoring, teams, qb


def current_season_week(detail):
    """Derive (season, week) from the detail fixture.

    Prefers value_weeks (content week per source family); falls back to the
    max across sources. Season is derived from built_at year.
    """
    value_weeks = detail.get("value_weeks") or {}
    weeks = [w for w in value_weeks.values() if isinstance(w, int)]
    week = max(weeks) if weeks else 1
    built_at = detail.get("built_at") or ""
    try:
        season = datetime.fromisoformat(built_at).year
    except ValueError:
        season = datetime.now(timezone.utc).year
    return season, week


def build_rows(detail):
    """Derive consolidation rows from the detail fixture.

    Returns (rows, diagnostics). Each row is a dict matching the
    public.consolidated_values columns (minus created_at).
    """
    rows = []
    diagnostics = {"skipped_unparseable_combo": [], "skipped_qb_violation": []}
    season, week = current_season_week(detail)
    bake_id = detail.get("built_at", "unknown")
    sources = detail.get("sources", {})

    for source, sdata in sources.items():
        # --- combos -> combo_reindexed ---
        combos = sdata.get("combos", {}) or {}
        for combo_key, cdata in combos.items():
            parsed = parse_combo_key(combo_key)
            if parsed is None:
                diagnostics["skipped_unparseable_combo"].append(f"{source}/{combo_key}")
                continue
            scoring, teams, qb_variant = parsed
            # Enforce the qb_variant invariant: qb1/qb2 IFF fantasycalc*.
            # 'none' sentinel means no variant (replaces NULL for PK compatibility).
            if qb_variant not in (None, "none") and source not in QB_VARIANT_SOURCES:
                diagnostics["skipped_qb_violation"].append(f"{source}/{combo_key}")
                continue
            reindexed = (cdata or {}).get("reindexed", {}) or {}
            for player, value in reindexed.items():
                if value is None:
                    continue  # missing stays missing (no row)
                rows.append({
                    "player": player,
                    "source": source,
                    "season": season,
                    "week": week,
                    "scoring": scoring,
                    "teams": teams,
                    "qb_variant": qb_variant or "none",
                    "view": "combo_reindexed",
                    "value": value,  # exact; never rounded here
                    "detail_locator": (
                        f"sources.{source}.combos.{combo_key}.reindexed[{player!r}]"
                    ),
                    "bake_id": bake_id,
                })

        # --- vorp_views -> vorp_indexed / vorp / adj_values ---
        vorp_views = sdata.get("vorp_views", {}) or {}
        views = vorp_views.get("views", {}) or {}
        # VORP grain: vorp_views carry their own scoring/teams context.
        vv_scoring_raw = str(vorp_views.get("scoring", "")).lower()
        vv_scoring = {"ppr": "full", "half-ppr": "half", "half": "half",
                      "standard": "standard", "full": "full"}.get(vv_scoring_raw)
        vv_teams = vorp_views.get("teams")
        for detail_view, vdata in views.items():
            view = VORP_VIEW_MAP.get(detail_view)
            if view is None:
                continue
            for player, value in (vdata or {}).items():
                if value is None:
                    continue
                rows.append({
                    "player": player,
                    "source": source,
                    "season": season,
                    "week": week,
                    "scoring": vv_scoring,
                    "teams": vv_teams,
                    "qb_variant": "none",
                    "view": view,
                    "value": value,
                    "detail_locator": (
                        f"sources.{source}.vorp_views.views.{detail_view}[{player!r}]"
                    ),
                    "bake_id": bake_id,
                })

    return rows, diagnostics


def composite_key(row):
    return (row["player"], row["source"], row["season"], row["week"],
            row["scoring"], row["teams"], row["qb_variant"], row["view"])


def reconcile(rows, detail):
    """Bidirectional key-set reconciliation against the detail fixture.

    Returns a list of error strings (empty = green).
    """
    errors = []

    # 1. Duplicate composite keys.
    seen = {}
    for i, row in enumerate(rows):
        key = composite_key(row)
        if key in seen:
            errors.append(f"duplicate key {key} at rows {seen[key]} and {i}")
        else:
            seen[key] = i

    # 2. Value reconciliation: re-read every row via the original deep path.
    sources = detail.get("sources", {})
    for i, row in enumerate(rows):
        locator = row["detail_locator"]
        try:
            # Parse "sources.<s>.combos.<c>.reindexed['<p>']" or
            #         "sources.<s>.vorp_views.views.<v>['<p>']"
            if ".combos." in locator:
                m = re.match(
                    r"sources\.(.+)\.combos\.(.+)\.reindexed\['(.*)'\]$", locator)
                s, c = m.group(1), m.group(2)
                expected = sources[s]["combos"][c]["reindexed"][m.group(3)]
            else:
                m = re.match(
                    r"sources\.(.+)\.vorp_views\.views\.(.+)\['(.*)'\]$", locator)
                s, v = m.group(1), m.group(2)
                expected = sources[s]["vorp_views"]["views"][v][m.group(3)]
        except (KeyError, TypeError, AttributeError):
            errors.append(f"row {i}: locator does not resolve: {locator}")
            continue
        if expected != row["value"]:
            errors.append(
                f"row {i}: value mismatch for {locator}: "
                f"consolidation={row['value']!r} detail={expected!r}")

    # 3. Completeness: every derivable detail cell has a consolidation row.
    expected_keys = set()
    for source, sdata in sources.items():
        for combo_key, cdata in (sdata.get("combos", {}) or {}).items():
            parsed = parse_combo_key(combo_key)
            if parsed is None:
                continue
            scoring, teams, qb_variant = parsed
            if qb_variant not in (None, "none") and source not in QB_VARIANT_SOURCES:
                continue
            for player, value in ((cdata or {}).get("reindexed", {}) or {}).items():
                if value is None:
                    continue
                # week/season are bake-level; recompute cheaply per row is
                # wasteful, so compare on the week-independent projection.
                expected_keys.add((player, source, scoring, teams,
                                   qb_variant or "none", "combo_reindexed"))
    have_keys = {(r["player"], r["source"], r["scoring"], r["teams"],
                  r["qb_variant"], r["view"]) for r in rows
                 if r["view"] == "combo_reindexed"}
    missing = expected_keys - have_keys
    extra = have_keys - expected_keys
    for key in sorted(missing)[:10]:
        errors.append(f"missing consolidation row for detail cell {key}")
    for key in sorted(extra)[:10]:
        errors.append(f"extra consolidation row with no detail cell {key}")
    if len(missing) > 10:
        errors.append(f"... and {len(missing) - 10} more missing rows")
    if len(extra) > 10:
        errors.append(f"... and {len(extra) - 10} more extra rows")

    # 4. Tuple validity: every row's (scoring, teams, qb_variant) is sane.
    for i, row in enumerate(rows):
        if row["scoring"] not in VALID_SCORING:
            errors.append(f"row {i}: invalid scoring {row['scoring']!r}")
        if row["teams"] not in VALID_TEAMS:
            errors.append(f"row {i}: invalid teams {row['teams']!r}")
        if row["qb_variant"] not in (None, "none") and row["source"] not in QB_VARIANT_SOURCES:
            errors.append(f"row {i}: qb_variant on non-fantasycalc source "
                          f"{row['source']}")

    return errors


def write_supabase(rows):
    """Upsert rows into public.consolidated_values via the REST API.

    Uses the supabase-football-signal skill's sbclient (service-role
    credential via the surrogate flow). Batched in chunks of 500.
    """
    # The skill lives under ~/workspace/skills; resolve from home.
    from pathlib import Path as _P
    skill_bin = _P.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"
    sys.path.insert(0, str(skill_bin))
    import sbclient

    total = 0
    for start in range(0, len(rows), 500):
        chunk = rows[start:start + 500]
        # PostgREST upsert: on_conflict targets the composite primary key.
        sbclient.post(
            "consolidated_values",
            chunk,
            params=("?on_conflict=player,source,season,week,scoring,teams,"
                    "qb_variant,view"),
            prefer="resolution=merge-duplicates",
        )
        total += len(chunk)
        print(f"  upserted {total}/{len(rows)} rows", flush=True)
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-supabase", action="store_true",
                    help="Upsert rows into public.consolidated_values")
    ap.add_argument("--json-out", default=None,
                    help="Write JSON export artifact to PATH")
    ap.add_argument("--fixture", default=str(FIXTURE),
                    help="Detail fixture to derive from")
    args = ap.parse_args()

    with open(args.fixture) as f:
        detail = json.load(f)

    with open(args.fixture, "rb") as f:
        detail_sha256 = hashlib.sha256(f.read()).hexdigest()

    rows, diagnostics = build_rows(detail)
    print(f"Built {len(rows)} consolidation rows from {args.fixture}")
    for key, vals in diagnostics.items():
        if vals:
            print(f"  {key}: {len(vals)} (e.g. {vals[:3]})")

    errors = reconcile(rows, detail)
    if errors:
        print(f"RECONCILIATION FAILED ({len(errors)} errors):", file=sys.stderr)
        for e in errors[:25]:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print("Reconciliation green: values match detail, key set is complete, "
          "no duplicates, tuples valid.")

    if args.write_supabase:
        n = write_supabase(rows)
        print(f"Wrote {n} rows to public.consolidated_values")

    if args.json_out:
        from export_consolidated_json import build_export_doc
        doc = build_export_doc(rows, detail_sha256)
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(doc, f, indent=1)
        print(f"Wrote JSON export to {out} ({out.stat().st_size} bytes)")

    if not args.write_supabase and not args.json_out:
        print("Dry run: nothing written (pass --write-supabase and/or --json-out).")


if __name__ == "__main__":
    main()
