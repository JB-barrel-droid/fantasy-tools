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

Write-time columns (live schema, JEG-377/380 hardening 2026-10-04/05; mirrored
in supabase/migrations/jeg377_jeg380_api_mirror.sql): public.consolidated_values
requires player_key (bigint NOT NULL, FK players), bake_uuid (uuid NOT NULL, FK
bakes) and source_generated_at (timestamptz NOT NULL, the source's CONTENT
vintage, JEG-380 "truthful freshness"). This builder sets them:
  * player_key: the fixture's own `player_keys` map (the keys the chart was
    baked with; no name matching here, so nothing fuzzy). A cell whose player
    has no key goes to review and is not written.
  * source_generated_at: per source, from the section's provenance
    (SGA_FIELDS order). Week-only vintages ("Week 5") fall back to the
    acquisition time `fetched_at`. No usable value -> fail closed.
  * bake_uuid: one public.bakes row per source per fixture (reused when the
    same fixture sha256 is re-run), created only after every pre-flight check
    passes.
Pre-flight (all before any write, fail closed with the list): every row has a
key, a bake and a vintage; every source is in public.source_config (FK); no
combo_reindexed value exceeds the table's cap (ck_combo_reindexed_cap, <= 70);
every player_key exists in public.players (FK).

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
COMBO_VALUE_CAP = 70  # live CHECK ck_combo_reindexed_cap (view <> combo_reindexed OR value <= 70)
CONTRACT_VERSION = "1.0.0"  # public.bakes.contract_version (pipelines/publish_gate.py)
# Content-vintage fields, most specific first (JEG-380: truthful source_generated_at).
SGA_FIELDS = (
    ("vintage",),                              # cbsros / razzball snapshot date
    ("espn_snapshot",),                        # ESPN projections snapshot date
    ("source_provenance", "content_vintage"),  # dated publications (FantasyPros, USA Today)
    ("lineage", "raw_vintage"),                # adjusted sections inherit the raw vintage
    ("fetched_at",),                           # week-labelled snapshots: acquisition time
)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
WRITE_REQUIRED = ("player_key", "bake_uuid", "source_generated_at", "created_at")
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
    public.consolidated_values columns except the write-time ones
    (bake_uuid, source_generated_at, created_at; see attach_write_fields).
    player_key comes from the fixture's own `player_keys`; a cell whose
    player has none is listed in diagnostics["review_no_player_key"] and
    not emitted (never guessed).
    """
    rows = []
    diagnostics = {"skipped_unparseable_combo": [], "skipped_qb_violation": [],
                   "review_no_player_key": []}
    season, week = current_season_week(detail)
    bake_id = detail.get("built_at", "unknown")
    sources = detail.get("sources", {})
    player_keys = detail.get("player_keys") or {}

    def keyed(row):
        key = player_keys.get(row["player"])
        if isinstance(key, bool) or not isinstance(key, int):
            diagnostics["review_no_player_key"].append(row["detail_locator"])
            return
        row["player_key"] = key
        rows.append(row)

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
                keyed({
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
                keyed({
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


def reconcile(rows, detail, review_locators=()):
    """Bidirectional key-set reconciliation against the detail fixture.

    review_locators: detail cells deliberately routed to review (no
    player_key); they are not "missing". Returns a list of error strings
    (empty = green).
    """
    errors = []
    reviewed = set(review_locators)

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
                if f"sources.{source}.combos.{combo_key}.reindexed[{player!r}]" in reviewed:
                    continue
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


# ---------------------------------------------------------------------------
# Write-time fields (NOT NULL in the live table)
# ---------------------------------------------------------------------------

def _parse_instant(value):
    """ISO date or datetime -> aware ISO string, else None ("Week 5" -> None)."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if len(text) == 10:
            dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        else:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.isoformat()


def source_generated_at_for(source, sdata):
    """(iso, field) for a source section's content vintage, or (None, None)."""
    for path in SGA_FIELDS:
        node = sdata
        for part in path:
            node = node.get(part) if isinstance(node, dict) else None
        iso = _parse_instant(node)
        if iso:
            return iso, ".".join(path)
    return None, None


def source_vintages(detail, sources):
    """{source: iso} for every source; SystemExit listing any without one."""
    out, missing = {}, []
    for src in sorted(sources):
        iso, _field = source_generated_at_for(src, detail["sources"].get(src) or {})
        if iso is None:
            missing.append(src)
        else:
            out[src] = iso
    if missing:
        raise SystemExit("FAIL-CLOSED: no content vintage (source_generated_at) in the fixture "
                         f"provenance for {missing}; looked at {['.'.join(p) for p in SGA_FIELDS]}")
    return out


def preflight(rows, known_sources):
    """Errors that the live table would reject, found before any write."""
    errors = []
    unknown = sorted({r["source"] for r in rows} - set(known_sources))
    if unknown:
        errors.append(f"sources not in public.source_config (FK fk_consolidated_values_source): {unknown}")
    over = [r for r in rows if r["view"] == "combo_reindexed" and r["value"] > COMBO_VALUE_CAP]
    if over:
        sample = ", ".join(f"{r['detail_locator']}={r['value']}" for r in over[:8])
        errors.append(f"{len(over)} combo_reindexed value(s) > {COMBO_VALUE_CAP} "
                      f"(CHECK ck_combo_reindexed_cap): {sample}")
    nokey = [r["detail_locator"] for r in rows if not isinstance(r.get("player_key"), int)]
    if nokey:
        errors.append(f"{len(nokey)} row(s) without player_key: {nokey[:5]}")
    return errors


def attach_write_fields(rows, bake_uuid_by_source, sga_by_source, created_at):
    """Rows ready for public.consolidated_values; SystemExit if any NOT NULL
    write field is missing or malformed (nothing is sent)."""
    out, bad = [], []
    for r in rows:
        w = dict(r, bake_uuid=bake_uuid_by_source.get(r["source"]),
                 source_generated_at=sga_by_source.get(r["source"]), created_at=created_at)
        problems = [f for f in WRITE_REQUIRED if w.get(f) in (None, "")]
        if w.get("player_key") is not None and (isinstance(w["player_key"], bool)
                                                or not isinstance(w["player_key"], int)):
            problems.append("player_key:not-int")
        if w.get("bake_uuid") and not UUID_RE.match(str(w["bake_uuid"])):
            problems.append("bake_uuid:not-uuid")
        if problems:
            bad.append((r["detail_locator"], problems))
        out.append(w)
    if bad:
        raise SystemExit(f"FAIL-CLOSED: {len(bad)} consolidated_values row(s) missing NOT NULL "
                         f"fields; nothing written. First: {bad[:5]}")
    return out


def _sbclient():
    # The skill lives under ~/workspace/skills (CI puts a shim on PYTHONPATH).
    skill_bin = Path.home() / "workspace" / "skills" / "supabase-football-signal" / "bin"
    sys.path.insert(0, str(skill_bin))
    import sbclient
    return sbclient


def bake_for_source(sb, source, sga, detail, detail_sha256):
    """public.bakes row for (source, this fixture): reused on a re-run of the
    same fixture, else created. Returns its uuid."""
    found = sb.get("bakes", params=(f"?select=bake_id&source=eq.{source}"
                                        f"&context->>fixture_sha256=eq.{detail_sha256}"
                                        "&order=ingested_at.desc&limit=1"))
    if isinstance(found, list) and found and found[0].get("bake_id"):
        return found[0]["bake_id"]
    created = sb.post("bakes", [{
        "source": source, "source_generated_at": sga, "contract_version": CONTRACT_VERSION,
        "context": {"writer": "build_consolidated_values.py", "original_bake_id": detail.get("built_at"),
                    "fixture_sha256": detail_sha256},
    }], prefer="return=representation")
    if not (isinstance(created, list) and created and created[0].get("bake_id")):
        raise SystemExit(f"FAIL-CLOSED: could not create a public.bakes row for {source}")
    return created[0]["bake_id"]


def write_supabase(rows, detail, detail_sha256, sb=None):
    """Write rows to public.consolidated_values, one bake per source.

    Every pre-flight check runs before the first write (bakes included).
    Rows are upserted on the primary key, source by source, in chunks of 500
    (the same PostgREST path as before the NOT NULL columns existed).
    """
    sb = sb or _sbclient()
    sources = sorted({r["source"] for r in rows})
    sga_by_source = source_vintages(detail, sources)
    known = [r.get("source") for r in sb.get("source_config", params="?select=source")]
    errors = preflight(rows, known)
    keys = sorted({r["player_key"] for r in rows if isinstance(r.get("player_key"), int)})
    have = {p.get("player_key") for p in sb.get_all("players", params="?select=player_key")}
    orphans = [k for k in keys if k not in have]
    if orphans:
        errors.append(f"{len(orphans)} player_key(s) not in public.players: {orphans[:10]}")
    if errors:
        raise SystemExit("FAIL-CLOSED: consolidated_values pre-flight failed; nothing written:\n  - "
                         + "\n  - ".join(errors))
    created_at = datetime.now(timezone.utc).isoformat()
    # Assemble once with a placeholder bake so a missing field fails before
    # any bake row is created.
    attach_write_fields(rows, {src: "00000000-0000-0000-0000-000000000000" for src in sources},
                        sga_by_source, created_at)
    bake_uuid_by_source = {}
    for src in sources:
        bake_uuid_by_source[src] = bake_for_source(sb, src, sga_by_source[src], detail, detail_sha256)
    ready = attach_write_fields(rows, bake_uuid_by_source, sga_by_source, created_at)
    total = 0
    for src in sources:
        batch = [r for r in ready if r["source"] == src]
        for start in range(0, len(batch), 500):
            sb.post("consolidated_values", batch[start:start + 500],
                    params=("?on_conflict=player,source,season,week,scoring,teams,"
                            "qb_variant,view"),
                    prefer="resolution=merge-duplicates,return=minimal")
        total += len(batch)
        print(f"  {src}: {len(batch)} rows (bake {bake_uuid_by_source[src]}, "
              f"source_generated_at {sga_by_source[src]})", flush=True)
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

    for locator in diagnostics.get("review_no_player_key", [])[:10]:
        print(f"  review (no player_key, not written): {locator}")
    errors = reconcile(rows, detail, diagnostics.get("review_no_player_key", ()))
    if errors:
        print(f"RECONCILIATION FAILED ({len(errors)} errors):", file=sys.stderr)
        for e in errors[:25]:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)
    print("Reconciliation green: values match detail, key set is complete, "
          "no duplicates, tuples valid.")

    if args.write_supabase:
        n = write_supabase(rows, detail, detail_sha256)
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
