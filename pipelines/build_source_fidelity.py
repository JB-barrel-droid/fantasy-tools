#!/usr/bin/env python3
"""Build source-fidelity.json: verify pre-indexed (native) values match sources exactly.

For each source (espn, cbsros, razzball, cbs, fantasycalc, fantasypros, usatoday):
  1. Read the fixture's native (pre-indexed, per-game) values
  2. Read the raw snapshot's native values (season totals)
  3. Convert raw to per-game and compare against fixture native
  4. Report exact-match status per player

The "unindexed curves" are the native values sorted by value per position.
The dashboard compares the source's unindexed curve against the pipeline's
unindexed curve (what feeds into the DDF calculation). They must match exactly.

Output: dist/modules/source-fidelity.json
"""

import json
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
RAW_DIR = REPO / "data" / "raw" / "sources"
OUTPUT = REPO / "dist" / "modules" / "source-fidelity.json"

SOURCES = ["espn", "cbs", "cbsros", "razzball", "fantasycalc", "fantasypros", "usatoday"]
SRC_LABEL = {
    "espn": "ESPN",
    "cbs": "CBS",
    "cbsros": "CBS ROS",
    "razzball": "Razzball",
    "fantasycalc": "FantasyCalc",
    "fantasypros": "FantasyPros",
    "usatoday": "USA Today",
}

# Games remaining for per-game conversion (2026 season, Week 4 = 14 games left? Actually check)
# For now, derive from the data itself

def load_fixture_natives():
    """fixture[source]['combos'][combo]['native'] -> {source: {combo: {slug: native}}}"""
    d = json.loads(FIXTURE.read_text())
    out = {}
    for src in SOURCES:
        src_data = d.get("sources", {}).get(src, {})
        out[src] = {}
        for combo_name, combo in src_data.get("combos", {}).items():
            native = combo.get("native", {})
            if native:
                out[src][combo_name] = dict(native)
    return out

def find_latest_snapshot(src):
    """Find the latest snapshot.json for a source."""
    src_dir = RAW_DIR / src
    if not src_dir.exists():
        return None
    # Find dated subdirectories, skipping archived/corrupt ones
    dated = sorted(
        [p for p in src_dir.iterdir() 
         if p.is_dir() and not p.name.startswith("_archived") and not p.name.startswith(".")],
        reverse=True
    )
    for d in dated:
        snap = d / "snapshot.json"
        if snap.exists():
            return snap
    # Try direct snapshot.json
    direct = src_dir / "snapshot.json"
    if direct.exists():
        return direct
    return None

def load_razzball_leg_natives():
    """Load Razzball per-game natives from committed 12-team DDF legs."""
    leg_dir = REPO / "data" / "ddf-two-tier"
    out = {}
    vintages = []
    if not leg_dir.exists():
        return out, None
    for leg_path in leg_dir.glob("*/ddf_leg_razzball.json"):
        try:
            leg = json.loads(leg_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        inputs = leg.get("inputs", {})
        if inputs.get("teams") != 12:
            continue
        scoring = inputs.get("scoring")
        if scoring not in {"ppr", "half_ppr", "standard"}:
            continue
        vintage = inputs.get("razzball_snapshot_date")
        if vintage:
            vintages.append(vintage)
        for row in leg.get("values", []):
            norm = str(row.get("player_norm", "")).strip()
            ppg = row.get("ppg")
            if norm and isinstance(ppg, (int, float)):
                out[(norm, scoring)] = float(ppg)
    return out, max(vintages) if vintages else None

def load_snapshot_natives(src):
    """Load source native values for fidelity comparison.
    
    For ESPN: uses the CSV input (ros_half_ppr / 16) which is the actual
    source the DDF leg reads. The snapshot has full-season totals which
    are not comparable to the ROS per-game natives.
    
    Returns: ({(player_norm, scoring): per_game_native}, vintage)
    """
    # Razzball: use the committed DDF legs. The raw snapshot is gitignored,
    # but every leg records Razzball's published PPG as the source native.
    if src == "razzball":
        return load_razzball_leg_natives()

    # CBS ROS: the snapshot already carries per-game natives per scoring
    # (per_game_ppr / per_game_half_ppr / per_game_standard), computed as
    # CBS ROS total / gp. Keys use the row's player_norm (the fixture join
    # norm), not the display name.
    if src == "cbsros":
        snap_path = find_latest_snapshot(src)
        if not snap_path:
            return {}, None
        d = json.loads(snap_path.read_text())
        out = {}
        pg_keys = {"ppr": "per_game_ppr", "half_ppr": "per_game_half_ppr",
                   "standard": "per_game_standard"}
        for row in d.get("rows", []):
            norm = str(row.get("player_norm", "")).strip()
            if not norm:
                continue
            for scoring, pg_key in pg_keys.items():
                val = row.get(pg_key)
                if isinstance(val, (int, float)):
                    out[(norm, scoring)] = float(val)
        return out, snap_path.parent.name if snap_path.parent != RAW_DIR / src else "direct"

    # ESPN: use the CSV input file directly
    if src == "espn":
        csv_path = REPO / "data" / "inputs" / "espn_projections.csv"
        if not csv_path.exists():
            return {}, None
        import csv as csv_mod
        out = {}
        vintage = None
        ineligible = set()
        with csv_path.open(newline="", encoding="utf-8") as f:
            for row in csv_mod.DictReader(f):
                norm = str(row.get("player_norm", "")).strip().lower()
                if not norm:
                    continue
                # Track ineligible players (IR/inactive) - they use ECR fill, not ESPN
                eligible = str(row.get("eligible", "")).strip().lower() in ("true", "1", "yes")
                if not eligible:
                    ineligible.add(norm)
                ros_half = row.get("ros_half_ppr")
                if ros_half:
                    try:
                        # DDF uses ROS / 16 (GAMES_DIVISOR)
                        per_game = float(ros_half) / 16
                        out[(norm, "half_ppr")] = per_game
                        # Also compute ppr and standard
                        rec = float(row.get("r_receptions", 0) or 0)
                        out[(norm, "ppr")] = (float(ros_half) + 0.5 * rec) / 16
                        out[(norm, "standard")] = (float(ros_half) - 0.5 * rec) / 16
                    except (ValueError, TypeError):
                        pass
                if not vintage:
                    vintage = row.get("espn_snapshot_date")
        # Store ineligible set for filtering
        out["_ineligible"] = ineligible
        return out, vintage
    
    # Other sources: use snapshot
    # For "reindexed-as-given" sources, the published value IS the pre-indexed native.
    # Which snapshot field is the fixture native's source of truth differs per
    # source: fantasypros was rebuilt from native_value on 2026-09-30 (the
    # flattening fix); fantasycalc/usatoday/cbs still build from value.
    # Comparing against the wrong field false-reds on a healthy pipeline.
    NATIVE_FIELD = {"fantasypros": "native_value"}
    field = NATIVE_FIELD.get(src, "value")
    fallback = "value" if field == "native_value" else "native_value"
    snap_path = find_latest_snapshot(src)
    if not snap_path:
        return {}, None
    d = json.loads(snap_path.read_text())
    out = {}
    for row in d.get("rows", []):
        name = str(row.get("player_name", "")).lower().strip()
        if not name:
            continue
        scoring = row.get("scoring", "")
        val = row.get(field)
        if val is None:
            val = row.get(fallback)
        if isinstance(val, (int, float)):
            out[(name, scoring)] = float(val)
    return out, snap_path.parent.name if snap_path.parent != RAW_DIR / src else "direct"

def main():
    fixture_natives = load_fixture_natives()
    
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {},
    }
    
    for src in SOURCES:
        snap_natives, snap_vintage = load_snapshot_natives(src)
        fixture_combos = fixture_natives.get(src, {})
        
        # Use full_12 or equivalent as the reference combo
        ref_combo = None
        for cand in ["full_12", "full_12_qb1", "half_12", "standard_12"]:
            if cand in fixture_combos:
                ref_combo = cand
                break
        if not ref_combo and fixture_combos:
            ref_combo = list(fixture_combos.keys())[0]
        
        src_report = {
            "label": SRC_LABEL[src],
            "snapshot_vintage": snap_vintage,
            "reference_combo": ref_combo,
            "status": "unk",
            "total_compared": 0,
            "exact_matches": 0,
            "mismatches": [],
            "sample_natives": [],  # Top 5 per position for dashboard display
            "unindexed_curve": {},  # pos -> sorted native values for curve viz
        }
        
        if not ref_combo or not snap_natives:
            src_report["status"] = "warn"
            src_report["reason"] = "No fixture native or snapshot data available"
            report["sources"][src] = src_report
            continue
        
        fixture_vals = fixture_combos[ref_combo]
        
        # Determine scoring/teams from combo name
        # full_12 -> ppr/full, 12 teams; half_12 -> half_ppr, 12 teams
        if ref_combo.startswith("full"):
            scoring = "ppr"
        elif ref_combo.startswith("half"):
            scoring = "half_ppr"
        elif ref_combo.startswith("standard") or ref_combo.startswith("std"):
            scoring = "standard"
        else:
            scoring = "ppr"
        teams = 12
        for t in [8, 10, 12, 14]:
            if f"_{t}" in ref_combo or f"_{t}_" in ref_combo:
                teams = t
                break
        
        # Compare: fixture native (per-game) vs source native (per-game)
        mismatches = []
        compared = 0
        matched = 0
        
        # Sample for dashboard: top players by native value
        sorted_fixture = sorted(fixture_vals.items(), key=lambda x: x[1], reverse=True)
        
        for slug, fix_native in sorted_fixture[:50]:  # Check top 50
            # Skip ineligible players (IR/inactive use ECR fill, not ESPN)
            if slug in snap_natives.get("_ineligible", set()):
                continue
            # Find in source natives (key is (name, scoring) for ESPN, (name, scoring) for others)
            src_val = snap_natives.get((slug, scoring))
            if src_val is None:
                # Try without scoring specificity (skip _ineligible marker)
                ineligible = snap_natives.get("_ineligible", set())
                for key, val in snap_natives.items():
                    if key == "_ineligible":
                        continue
                    name, sc = key
                    if name == slug:
                        src_val = val
                        break
            
            if src_val is None:
                continue
            
            compared += 1
            # Exact match with small tolerance for floating point
            if abs(fix_native - src_val) < 0.01:
                matched += 1
            else:
                mismatches.append({
                    "player": slug,
                    "fixture_native": fix_native,
                    "source_native": round(src_val, 3),
                    "diff": round(fix_native - src_val, 3),
                })
        
        src_report["total_compared"] = compared
        src_report["exact_matches"] = matched
        src_report["mismatches"] = mismatches[:10]  # Top 10 mismatches
        
        if compared == 0:
            src_report["status"] = "warn"
            src_report["reason"] = "No comparable players found"
        elif mismatches:
            src_report["status"] = "bad"
            src_report["reason"] = f"{len(mismatches)} mismatches out of {compared} compared"
        else:
            src_report["status"] = "ok"
            src_report["reason"] = f"All {compared} compared values match exactly"
        
        # Build unindexed curve data: top 20 natives per position
        # Need position info - load from players
        try:
            players = json.loads((REPO / "data" / "fixtures" / "current" / "players.json").read_text())["players"]
            pos_by_slug = {}
            # Build slug->pos via player_keys
            fixture_data = json.loads(FIXTURE.read_text())
            player_keys = fixture_data.get("player_keys", {})
            key_to_pos = {p["player_key"]: p["pos"] for p in players if p.get("player_key")}
            for slug, key in player_keys.items():
                if key in key_to_pos:
                    pos_by_slug[slug] = key_to_pos[key]
        except:
            pos_by_slug = {}
        
        for pos in ["QB", "RB", "WR", "TE"]:
            pos_vals = [(s, v) for s, v in fixture_vals.items() if pos_by_slug.get(s) == pos]
            pos_vals.sort(key=lambda x: x[1], reverse=True)
            src_report["unindexed_curve"][pos] = [
                {"player": s, "native": v} for s, v in pos_vals[:20]
            ]
        
        # Sample natives for display
        for pos in ["QB", "RB", "WR", "TE"]:
            curve = src_report["unindexed_curve"][pos]
            if curve:
                src_report["sample_natives"].append({
                    "pos": pos,
                    "top": curve[0],
                })
        
        report["sources"][src] = src_report
    
    OUTPUT.write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT}")
    
    # Summary
    for src, r in report["sources"].items():
        print(f"  {src}: {r['status']} - {r['reason']}")

if __name__ == "__main__":
    main()
