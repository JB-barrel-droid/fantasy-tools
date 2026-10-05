#!/usr/bin/env python3
"""Load the canonical weekly signals bundle into the Supabase weekly dashboard tables.

Source of truth: the newest staged_bundle_*.json produced by the weekly
signals dashboard refresh (lottery/bin/build_weekly_dashboards.py), found under
~/workspace/goals/football-signal-database-and-app/hidden_files/weekly_dashboard_refresh_*/.

Idempotent: a run is keyed on (week, bundle file, bundle built_at). If the
current run already covers the newest bundle, the loader exits 0 with NOOP.

Dedupe: the engine emits one row per player, but some players get a full
signal row plus a no_market_read stub. Keep the richer row per player_key:
prefer a populated vegas_leg, then coverage_ok, then most non-null fields.

Fail-closed: missing bundle, zero rows after dedupe, or a post-load view
count mismatch all exit non-zero with a loud message. Nothing is half-wired:
the run row is inserted first, signals are batched in, and the is_current
flip happens only after every signal row is read back.

Usage:
    python3 pipelines/load_weekly_dashboard.py
Exit codes: 0 ok / no-op, 2 blocked (missing input or verification failure).
"""

import glob
import json
import os
import sys

SKILL_BIN = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
sys.path.insert(0, SKILL_BIN)
sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import sbclient  # noqa: E402

BUNDLE_GLOB = os.path.expanduser(
    "~/workspace/goals/football-signal-database-and-app/hidden_files/"
    "weekly_dashboard_refresh_*/staged_bundle_*.json"
)
BATCH = 100


def fail(msg, code=2):
    print(f"BLOCKED: {msg}", file=sys.stderr)
    sys.exit(code)


def newest_bundle():
    files = sorted(glob.glob(BUNDLE_GLOB), key=os.path.getmtime)
    if not files:
        fail("no staged weekly signals bundle found under weekly_dashboard_refresh_*/")
    return files[-1]


def richness(row):
    """Score a signal row; the full row beats the no_market_read stub."""
    score = 0
    if row.get("vegas_leg"):
        score += 1000
    if row.get("coverage_ok"):
        score += 100
    score += sum(1 for v in row.values() if v is not None)
    return score


def dedupe(players):
    best = {}
    for row in players:
        key = (row.get("player_key") or "").strip().lower()
        if not key:
            continue
        if key not in best or richness(row) > richness(best[key]):
            best[key] = row
    return best


def main():
    bundle_path = newest_bundle()
    bundle = json.load(open(bundle_path))
    meta = bundle.get("meta", {})
    players = bundle.get("players", [])
    week = meta.get("week")
    season = meta.get("season", 2026)
    built_at = meta.get("built_at")
    if not week or not players:
        fail(f"bundle {bundle_path} missing week or players")
    rows = dedupe(players)
    if not rows:
        fail("dedupe produced zero rows")

    manifest = {
        "engine": "v4",
        "loader": "pipelines/load_weekly_dashboard.py",
        "bundle": os.path.basename(bundle_path),
        "bundle_path": bundle_path,
        "bundle_built_at": built_at,
        "bundle_source_file": meta.get("source_file"),
        "n_bundle_players": len(players),
        "n_deduped": len(rows),
    }

    # Idempotency: no-op if the current run already covers this exact bundle.
    runs = sbclient.get(
        "weekly_dashboard_runs",
        "?select=run_id,week,is_current,source_manifest&order=created_at.desc&limit=5",
    )
    for r in runs:
        m = r.get("source_manifest") or {}
        if (
            r.get("week") == week
            and m.get("bundle") == manifest["bundle"]
            and m.get("bundle_built_at") == built_at
            and r.get("is_current")
        ):
            print(f"NOOP: week {week} bundle {manifest['bundle']} already current (run {r['run_id']})")
            return 0

    run_rows = sbclient.post(
        "weekly_dashboard_runs",
        {"week": week, "season": season, "source_manifest": manifest, "is_current": False},
    )
    run_id = run_rows[0]["run_id"]
    print(f"run {run_id} created for week {week} ({len(rows)} players)")

    items = [
        {
            "run_id": run_id,
            "player_key": key,
            "position": row.get("pos") or None,
            "team": row.get("team") or None,
            "signal": row,
        }
        for key, row in rows.items()
    ]
    for i in range(0, len(items), BATCH):
        sbclient.post("weekly_dashboard_signals", items[i : i + BATCH], prefer="return=minimal")
    print(f"inserted {len(items)} signal rows")

    # Flip current only after all signals are read back.
    got = sbclient.get(
        "weekly_dashboard_signals",
        f"?select=player_key&run_id=eq.{run_id}&limit={len(items) + 1}",
    )
    if len(got) != len(items):
        fail(
            f"signal count mismatch: wrote {len(items)}, read back {len(got)} "
            f"(run {run_id} left non-current)"
        )
    for r in runs:
        if r["run_id"] != run_id and r.get("is_current"):
            sbclient.patch("weekly_dashboard_runs", {"is_current": False}, f"?run_id=eq.{r['run_id']}")
    sbclient.patch("weekly_dashboard_runs", {"is_current": True}, f"?run_id=eq.{run_id}")

    check = sbclient.get("v_current_weekly_signals", f"?select=player_key&limit={len(items) + 1}")
    if len(check) != len(items):
        fail(f"view count mismatch: expected {len(items)}, view returned {len(check)}")
    print(f"OK: week {week} current with {len(items)} rows (run {run_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
