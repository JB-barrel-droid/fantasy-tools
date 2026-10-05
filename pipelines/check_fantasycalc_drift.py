#!/usr/bin/env python3
"""Check FantasyCalc live API vs snapshot native values; trigger refresh on drift.

Standing rule (2026-09-30, Jeremy): the project reruns the FantasyCalc
pipelines when native doesn't match live. This script is the trigger.

Compares the live FantasyCalc API (redraft, 12 teams, 0.5 PPR, 1 QB --
the representative combo) against the snapshot's native_value field.
If drift exceeds the threshold, exits 1 (drift detected) and optionally
runs the full refresh pipeline with --trigger.

Usage:
  check_fantasycalc_drift.py [--trigger] [--threshold PCT]

Exit codes:
  0 = no significant drift, snapshot is fresh
  1 = drift detected (refresh needed)
  2 = check failed (API unreachable, snapshot missing, etc.)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO / "data/raw/sources/fantasycalc/week-4/snapshot.json"
API_URL = ("https://api.fantasycalc.com/values/current"
           "?isDynasty=false&numQbs=1&numTeams=12&ppr=0.5")

# Drift threshold: fraction of sampled values that must move by more than
# 5% to trigger a refresh. FantasyCalc updates through the day; 1-3% intraday
# moves are normal noise. A broad 5%+ shift across 20%+ of the sample means
# the snapshot is genuinely stale or corrupted (like the 2026-09-30 JSN defect
# where natives were off by 99%).
DEFAULT_THRESHOLD = 0.20
MOVE_PCT = 0.05
SAMPLE_N = 25


def fetch_live() -> dict[str, float]:
    req = urllib.request.Request(API_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    out = {}
    for p in data:
        pl = p.get("player", {})
        name = pl.get("name")
        val = p.get("value")
        if name and val is not None:
            out[name] = float(val)
    return out


def load_snapshot_natives() -> dict[str, float]:
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(f"snapshot missing: {SNAPSHOT_PATH}")
    snap = json.load(open(SNAPSHOT_PATH))
    out = {}
    for row in snap.get("rows", []):
        if row.get("scoring") == "half_ppr" and row.get("teams") == 12:
            nv = row.get("native_value", row.get("value"))
            if row.get("player_name") and nv is not None:
                out[row["player_name"]] = float(nv)
    return out


def check_drift(threshold: float = DEFAULT_THRESHOLD) -> dict:
    live = fetch_live()
    natives = load_snapshot_natives()
    if not live:
        raise RuntimeError("live API returned no players")
    if not natives:
        raise RuntimeError("snapshot has no half_ppr/12 natives")

    # Sample the top-N by live value (these matter most for the chart)
    top_live = sorted(live.items(), key=lambda kv: kv[1], reverse=True)[:SAMPLE_N]
    moved = 0
    details = []
    for name, live_val in top_live:
        native_val = natives.get(name)
        if native_val is None:
            moved += 1
            details.append((name, live_val, None, "missing from snapshot"))
            continue
        if native_val == 0:
            continue
        pct_move = abs(live_val - native_val) / native_val
        if pct_move > MOVE_PCT:
            moved += 1
            details.append((name, live_val, native_val, f"{pct_move:.1%}"))
    drift_frac = moved / len(top_live) if top_live else 0.0
    return {
        "drift_frac": drift_frac,
        "moved": moved,
        "sampled": len(top_live),
        "threshold": threshold,
        "needs_refresh": drift_frac > threshold,
        "details": details[:10],
        "live_top3": [n for n, _ in top_live[:3]],
    }


def run_refresh_pipeline() -> int:
    """Run the full FantasyCalc refresh: snapshot -> match -> reference ->
    section -> reindex -> fixture -> monitors."""
    steps = [
        # Snapshot is refreshed by the caller (this script's --trigger path
        # pulls fresh API data before invoking the pipeline).
        ["python3", "pipelines/match_source_snapshot.py",
         "--input", "data/raw/sources/fantasycalc/week-4/snapshot.json"],
    ]
    for cmd in steps:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAILED: {' '.join(cmd)}\n{r.stderr}", file=sys.stderr)
            return r.returncode
        print(r.stdout.strip().split("\n")[-1])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trigger", action="store_true",
                    help="run the refresh pipeline if drift is detected")
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    args = ap.parse_args()

    try:
        result = check_drift(args.threshold)
    except Exception as e:
        print(f"DRIFT CHECK FAILED: {e}", file=sys.stderr)
        return 2

    print(f"drift: {result['moved']}/{result['sampled']} "
          f"({result['drift_frac']:.1%}) vs threshold {result['threshold']:.1%}")
    for name, live_v, nat_v, note in result["details"]:
        print(f"  {name}: live={live_v:.0f} native={nat_v} ({note})")
    print(f"live top 3: {', '.join(result['live_top3'])}")

    if not result["needs_refresh"]:
        print("OK: snapshot is fresh, no refresh needed")
        return 0

    print("DRIFT DETECTED: snapshot natives do not match live")
    if not args.trigger:
        print("re-run with --trigger to refresh the pipelines")
        return 1

    print("triggering FantasyCalc pipeline refresh...")
    # Refresh the snapshot from the live API first. Fetch all team sizes the
    # chart serves (Jeremy 2026-10-04: the old 12-team-only refresh left the
    # 8/10/14 combos stale on every drift cycle).
    from datetime import datetime, timezone
    combos = []
    combo_counts = {}
    for scoring, ppr in [("standard", 0), ("half_ppr", 0.5), ("ppr", 1.0)]:
        for teams in (8, 10, 12, 14):
            url = (f"https://api.fantasycalc.com/values/current?isDynasty=false"
                   f"&numQbs=1&numTeams={teams}&ppr={ppr}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.load(resp)
            combo_counts[(scoring, teams)] = len(data)
            for p in data:
                pl = p.get("player", {})
                if pl.get("name") and p.get("value") is not None:
                    combos.append({
                        "player_name": pl["name"],
                        "pos": pl.get("position"),
                        "team": pl.get("team"),
                        "source_player_id": pl.get("id"),
                        "scoring": scoring,
                        "teams": teams,
                        "native_value": float(p["value"]),
                        "value": float(p["value"]),
                    })
            print(f"  fetched {scoring}/{teams}: {len(data)} players", flush=True)
    # Fail-closed: never overwrite the snapshot with a partial pull.
    # 2026-10-05: a transient API outage returned 594/2376 rows; the partial
    # snapshot flowed into a 588-row table write two mornings running.
    prior_snap = json.load(open(SNAPSHOT_PATH))
    prior_rows = prior_snap.get("row_count") or len(prior_snap.get("rows", []))
    bad_combos = [f"{s}/{t}" for (s, t), n in combo_counts.items() if n < 150]
    if bad_combos or len(combos) < 0.9 * prior_rows:
        print(f"FAIL-CLOSED: partial FantasyCalc pull: {len(combos)} rows "
              f"(prior snapshot {prior_rows}), bad combos: {bad_combos}; "
              f"snapshot untouched", file=sys.stderr)
        return 2
    snap = prior_snap
    snap["rows"] = combos
    snap["row_count"] = len(combos)
    snap["fetched_at"] = datetime.now(timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S+00:00")
    snap["review_count"] = 0
    snap["review_rows"] = []
    with open(SNAPSHOT_PATH, "w") as f:
        json.dump(snap, f, indent=2)
    print(f"snapshot refreshed: {len(combos)} rows")

    # Now run match -> reference -> section -> reindex
    import glob
    seq = [
        ["python3", "pipelines/match_source_snapshot.py",
         "--input", str(SNAPSHOT_PATH.relative_to(REPO))],
    ]
    for cmd in seq:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"FAILED: {' '.join(cmd)}\n{r.stderr}", file=sys.stderr)
            return 1
        print(r.stdout.strip().split("\n")[-1])

    # Find the match output and build references
    matches = sorted(glob.glob(
        str(REPO / "output/source-matches/fantasycalc/*/fantasycalc-*-matched.json")))
    if not matches:
        print("no match output found", file=sys.stderr)
        return 1
    r = subprocess.run(
        ["python3", "pipelines/build_source_reference.py",
         "--input", matches[-1]],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"reference build failed\n{r.stderr}", file=sys.stderr)
        return 1
    print(r.stdout.strip().split("\n")[-1])

    refs = sorted(glob.glob(str(
        REPO / "output/source-references/fantasycalc" /
        datetime.now(timezone.utc).strftime("%Y-%m-%d") / "*.json")))
    if not refs:
        print("no reference outputs found", file=sys.stderr)
        return 1
    r = subprocess.run(
        ["python3", "pipelines/build_comparison_source_section.py",
         "--input"] + refs,
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"section build failed\n{r.stderr}", file=sys.stderr)
        return 1
    print(r.stdout.strip().split("\n")[-1])

    cands = sorted(glob.glob(str(
        REPO / "output/comparison-candidates/fantasycalc/*/*.json")))
    if not cands:
        print("no candidate section found", file=sys.stderr)
        return 1
    r = subprocess.run(
        ["python3", "pipelines/reindex_comparison_section.py", cands[-1]],
        cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"reindex failed\n{r.stderr}", file=sys.stderr)
        return 1
    print("reindex complete")

    # Update the fixture from the reindexed output
    reidx_files = sorted(glob.glob(str(
        REPO / "output/comparison-reference/fantasycalc-*-reindexed.json")))
    if not reidx_files:
        print("no reindexed output found", file=sys.stderr)
        return 1
    reidx = json.load(open(reidx_files[-1]))
    fix_path = REPO / "data/fixtures/current/comparison-sources-data.json"
    fix = json.load(open(fix_path))
    fc = fix["sources"]["fantasycalc"]
    for combo_key, combo_data in reidx["combos"].items():
        if combo_key in fc["combos"]:
            fc["combos"][combo_key]["native"] = combo_data.get("native", {})
            fc["combos"][combo_key]["reindexed"] = combo_data.get(
                "reindexed", {})
            # JEG-366: carry fit + index_total through the fixture update.
            # Dropping either left review_comparison_candidate.py in a
            # permanent coverage hold (the n_priced counts and pre_total
            # sanity check both depend on these). Index_total is the
            # pos-level pie totals; fit is the VORP-overlap scaling
            # metadata the fixture must keep in sync with the reindexer.
            fc["combos"][combo_key]["index_total"] = combo_data.get(
                "index_total", {})
            fc["combos"][combo_key]["fit"] = combo_data.get("fit", {})
            fc["combos"][combo_key]["n"] = len(combo_data.get("native", {}))
    fc["fetched_at"] = snap["fetched_at"]
    with open(fix_path, "w") as f:
        json.dump(fix, f, indent=2)
    # Sync the served copies
    for dest in ["app/trade-value-chart/assets/comparison-sources-data.json",
                 "dist/assets/comparison-sources-data.json"]:
        (REPO / dest).write_text(json.dumps(fix, indent=2))
    print("fixture updated and synced")

    # Rebuild the monitors
    for builder in ["pipelines/build_source_fidelity.py",
                    "pipelines/build_index_math.py",
                    "pipelines/build_source_value_lineage.py"]:
        r = subprocess.run(["python3", builder], cwd=REPO,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{builder} failed\n{r.stderr}", file=sys.stderr)
            return 1
    print("monitors rebuilt")
    print("REFRESH COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
