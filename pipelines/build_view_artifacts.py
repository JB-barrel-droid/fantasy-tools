#!/usr/bin/env python3
"""JEG-265: build per-view addressable JSON artifacts (vorp-view.json, adj-view.json).

Both artifacts read the same source-value-lineage.json the dashboard already
consumes, but expose only the columns and verdicts that belong to one view.
Wired into pipelines/sync_dashboard_artifacts.py so `make sync` copies them
into dist/modules/ alongside the dashboard.

VORP view: group / alloc_factor / our_group_vorp / imputed_vorp columns per
source + the VORP round-trip block per source. Status is ok when every source
has a populated imputed_vorp and an absent (error-only) round-trip error;
warn when round-trip carries a partial warning; bad when a source has nulls
where the Option C 8-group input was expected.

Adj view: indexed / index_mult / reweighted / reweight_mult / chart_value
columns per source. Status is ok when every source's chart column matches
its indexed value, warn when partial coverage, bad on mismatch or null chart.

Both artifacts fail-closed: a missing lineage.json raises FileNotFoundError
(never emits a partial/empty file). Standalone-builder friendly: no Supabase,
no scrape requirement -- reads only the lineage artifact the prior step wrote.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINEAGE_PATH = os.path.join(REPO, "dist/modules/source-value-lineage.json")
VORP_OUT = os.path.join(REPO, "dist/modules/vorp-view.json")
ADJ_OUT = os.path.join(REPO, "dist/modules/adj-view.json")

VORP_COLS = ("group", "alloc_factor", "our_group_vorp", "imputed_vorp")
ADJ_COLS = ("indexed", "index_mult", "reweighted", "reweight_mult", "chart_value")


def _load_lineage():
    if not os.path.exists(LINEAGE_PATH):
        raise FileNotFoundError(
            f"Lineage artifact missing: {LINEAGE_PATH}. "
            "Run pipelines/build_source_value_lineage.py first."
        )
    with open(LINEAGE_PATH) as f:
        return json.load(f)


def _pick(rows, cols, n=3):
    """Pick n rows from rows[*], each reduced to just cols."""
    out = []
    for r in rows[:n]:
        slim = {"player": r.get("player_key") or r.get("player") or r.get("name")}
        for c in cols:
            slim[c] = r.get(c)
        out.append(slim)
    return out


SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


def _row_vorp_status(row):
    """OK when imputed_vorp present; bad when group assigned but imputed_vorp
    null; bad when a skill-position row has no group at all (nulls where the
    Option C 8-group input was expected -- never a silent skip). Rows with no
    skill position (untracked grain) are skipped."""
    group = row.get("group")
    pos = (row.get("vorp_inferred_position") or "").upper()
    if group is None:
        if pos in SKILL_POSITIONS:
            return "bad"
        return None  # No skill position (untracked) -- skip
    if row.get("imputed_vorp") is not None:
        return "ok"
    return "bad"


def _row_adj_status(row):
    """OK when chart_value matches indexed; bad on mismatch; warn when n/a."""
    indexed = row.get("indexed")
    chart = row.get("chart_value")
    if indexed is None:
        return None
    if chart is None:
        return None
    if row.get("chart_matches_indexed") is False:
        return "bad"
    return "ok"


def _aggregate(source_statuses):
    if not source_statuses:
        return "unk"
    if any(s == "bad" for s in source_statuses):
        return "bad"
    if all(s == "ok" for s in source_statuses):
        return "ok"
    return "warn"


def build_vorp_view(lineage):
    sources_out = {}
    statuses = []
    for src_key, src in (lineage.get("sources") or {}).items():
        rows = src.get("top25") or []
        row_statuses = []
        slim_rows = []
        for r in rows:
            slim = {"player": r.get("player_key")}
            for col in VORP_COLS:
                slim[col] = r.get(col)
            slim_rows.append(slim)
            st = _row_vorp_status(r)
            if st is not None:
                row_statuses.append(st)
        rt = src.get("vorp_round_trip") or {}
        rt_status = "ok"
        reasons = []
        if rt.get("error"):
            rt_status = "bad"
            reasons.append(f"VORP round-trip error: {rt.get('error')}")
        # group_placeholder signals ddf-group-vorps.json was missing -> warn
        if src.get("group_placeholder"):
            reasons.append("group_placeholder: JEG-206 artifact absent")
            if rt_status == "ok":
                rt_status = "warn"
        # Source-level status: worst of (row, rt)
        src_status = _aggregate(row_statuses + [rt_status]) if row_statuses else rt_status
        statuses.append(src_status)
        sources_out[src_key] = {
            "label": src.get("label") or src_key,
            "status": src_status,
            "reason": ("VORP view healthy" if src_status == "ok" else
                       ("VORP view degraded" if src_status == "warn" else "VORP view failed")),
            "reasons": reasons,
            "samples": _pick(slim_rows, VORP_COLS, n=3),
            "vorp_round_trip": {
                "status": rt_status,
                "error": rt.get("error"),
                "inherited_from": rt.get("inherited_from"),
            } if rt else None,
        }
    overall = _aggregate(statuses)
    return {
        "view": "vorp",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": overall,
        "columns": list(VORP_COLS),
        "sources": sources_out,
        "source_count": len(sources_out),
    }


def build_adj_view(lineage):
    sources_out = {}
    statuses = []
    for src_key, src in (lineage.get("sources") or {}).items():
        rows = src.get("top25") or []
        row_statuses = []
        slim_rows = []
        for r in rows:
            slim = {"player": r.get("player_key")}
            for col in ADJ_COLS:
                slim[col] = r.get(col)
            slim_rows.append(slim)
            st = _row_adj_status(r)
            if st is not None:
                row_statuses.append(st)
        # Source-level status: include legacy artifact flags if present
        legacy_flags = src.get("legacy_artifact_flags") or []
        src_status = _aggregate(row_statuses) if row_statuses else "unk"
        reasons = list(legacy_flags)
        if src_status == "bad":
            reasons.append("chart_value does not match indexed value")
        statuses.append(src_status)
        sources_out[src_key] = {
            "label": src.get("label") or src_key,
            "status": src_status,
            "reason": ("Adj view healthy" if src_status == "ok" else
                       ("Adj view degraded" if src_status == "warn" else "Adj view failed")),
            "reasons": reasons,
            "samples": _pick(slim_rows, ADJ_COLS, n=3),
        }
    overall = _aggregate(statuses)
    return {
        "view": "adj",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": overall,
        "columns": list(ADJ_COLS),
        "sources": sources_out,
        "source_count": len(sources_out),
    }


def main():
    lineage = _load_lineage()
    v = build_vorp_view(lineage)
    a = build_adj_view(lineage)
    with open(VORP_OUT, "w") as f:
        json.dump(v, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(ADJ_OUT, "w") as f:
        json.dump(a, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"Wrote {VORP_OUT} (status={v['status']}, sources={v['source_count']})")
    print(f"Wrote {ADJ_OUT} (status={a['status']}, sources={a['source_count']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())