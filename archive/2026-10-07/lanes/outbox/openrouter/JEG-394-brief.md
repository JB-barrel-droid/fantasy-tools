# Brief: JEG-394 — deterministic bundle selection, dedupe, idempotency for the weekly loader

## Task
Rewrite `pipelines/load_weekly_dashboard.py` (full current source embedded
below) to eliminate three nondeterminism sources. Output the COMPLETE revised
file (not a diff) plus a short note on what changed and why. Do not apply
anything — Roman reviews and integrates.

## Problems (all confirmed)
1. Bundle selection is by filesystem mtime (`newest_bundle()`), ignoring
   season/week metadata. A stale or wrong-week file can be published.
2. Dedupe uses a heuristic `richness()` score. The engine emits, per player,
   one FULL signal row (has `vegas_leg`, e.g. "propline") plus one
   `no_market_read` STUB row (`vegas_leg` absent/null, thin fields). A changed
   stub shape could out-score the full row. Week-4 bundle: 505 rows,
   390 unique players, 115 full/stub pairs.
3. Idempotency key is (week, bundle filename, bundle built_at), checked
   against only the 5 latest runs, with no season in the key. A rebuilt
   bundle with identical metadata but changed contents is skipped; copying
   the same bundle under a new filename double-loads (observed live).

## Bundle row shape (flat dict per player)
Keys include: player_key, pos, name, team, vegas_std, vegas_half, vegas_ppr,
expert_std, expert_half, expert_ppr, pts_delta_ppr, vegas_pos_rank,
ecr_pos_rank, ecr_official, n_pos, delta, abs_delta, direction, pos_level_gap,
pts_delta_adj, post_worthy, worthy_reason, td_p_yes, expert_td_exp,
vegas_provenance, vegas_leg, coverage_ok. Meta: {week, season, built_at,
source_file, n_players, ...}.

## Requirements
1. Bundle selection: `--bundle PATH` (already exists) or `WEEKLY_BUNDLE_PATH`
   (already exists) is mandatory in CI; the VM-mtime fallback stays for local
   use. Validate meta.week/meta.season/meta.built_at present and sane; fail
   closed otherwise. Accept an expected week (arg/env `EXPECTED_WEEK`) and
   refuse to publish when bundle week != expected.
2. Dedupe: explicit classification — a row is FULL iff it has a non-null
   `vegas_leg`; STUB otherwise. Per normalized player_key keep the FULL row;
   fail closed on two FULL rows for one key or any unrecognized duplicate
   shape. No scores.
3. Manifest: add `bundle_sha256` (hex of the file bytes) + season. Idempotency:
   query the CURRENT run (not latest-5); NOOP only when current run's
   (season, week, bundle_sha256) all match. Reject publishing an older
   (season, week) or an older built_at for the same week unless
   `--allow-rollback` is passed (audited in the manifest).
4. Keep: batch inserts, pre-promotion read-back verification, fail-closed
   exit codes (0 ok/no-op, 2 blocked). Keep the sbclient import fallback
   (skill bin → CI shim) and `--bundle` plumbing as-is.

## Current source
```python
#!/usr/bin/env python3
"""Load the canonical weekly signals bundle into the Supabase weekly dashboard tables. ... """
import argparse
import glob
import json
import os
import sys
SKILL_BIN = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
if os.path.isdir(SKILL_BIN):
    sys.path.insert(0, SKILL_BIN)
sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import sbclient
BUNDLE_GLOB = os.path.expanduser(
    "~/workspace/goals/football-signal-database-and-app/hidden_files/"
    "weekly_dashboard_refresh_*/staged_bundle_*.json")
BATCH = 100
def fail(msg, code=2):
    print(f"BLOCKED: {msg}", file=sys.stderr); sys.exit(code)
def newest_bundle(explicit=None):
    if explicit:
        if not os.path.isfile(explicit): fail(f"bundle not found: {explicit}")
        return explicit
    env_path = os.environ.get("WEEKLY_BUNDLE_PATH")
    if env_path:
        if not os.path.isfile(env_path): fail(f"WEEKLY_BUNDLE_PATH not found: {env_path}")
        return env_path
    files = sorted(glob.glob(BUNDLE_GLOB), key=os.path.getmtime)
    if not files: fail("no staged weekly signals bundle found under weekly_dashboard_refresh_*/")
    return files[-1]
def richness(row):
    score = 0
    if row.get("vegas_leg"): score += 1000
    if row.get("coverage_ok"): score += 100
    score += sum(1 for v in row.values() if v is not None)
    return score
def dedupe(players):
    best = {}
    for row in players:
        key = (row.get("player_key") or "").strip().lower()
        if not key: continue
        if key not in best or richness(row) > richness(best[key]): best[key] = row
    return best
def main(argv=None):
    ap = argparse.ArgumentParser(description="Load the weekly signals bundle into Supabase.")
    ap.add_argument("--bundle", default=None, help="Explicit bundle path.")
    args = ap.parse_args(argv)
    bundle_path = newest_bundle(args.bundle)
    bundle = json.load(open(bundle_path))
    meta = bundle.get("meta", {}); players = bundle.get("players", [])
    week = meta.get("week"); season = meta.get("season", 2026); built_at = meta.get("built_at")
    if not week or not players: fail(f"bundle {bundle_path} missing week or players")
    rows = dedupe(players)
    if not rows: fail("dedupe produced zero rows")
    manifest = {"engine": "v4", "loader": "pipelines/load_weekly_dashboard.py",
        "bundle": os.path.basename(bundle_path), "bundle_path": bundle_path,
        "bundle_built_at": built_at, "bundle_source_file": meta.get("source_file"),
        "n_bundle_players": len(players), "n_deduped": len(rows)}
    runs = sbclient.get("weekly_dashboard_runs",
        "?select=run_id,week,is_current,source_manifest&order=created_at.desc&limit=5")
    for r in runs:
        m = r.get("source_manifest") or {}
        if (r.get("week") == week and m.get("bundle") == manifest["bundle"]
                and m.get("bundle_built_at") == built_at and r.get("is_current")):
            print(f"NOOP: week {week} bundle {manifest['bundle']} already current"); return 0
    run_rows = sbclient.post("weekly_dashboard_runs",
        {"week": week, "season": season, "source_manifest": manifest, "is_current": False})
    run_id = run_rows[0]["run_id"]
    items = [{"run_id": run_id, "player_key": key,
              "position": row.get("pos") or None, "team": row.get("team") or None,
              "signal": row} for key, row in rows.items()]
    for i in range(0, len(items), BATCH):
        sbclient.post("weekly_dashboard_signals", items[i:i+BATCH], prefer="return=minimal")
    got = sbclient.get("weekly_dashboard_signals",
        f"?select=player_key&run_id=eq.{run_id}&limit={len(items)+1}")
    if len(got) != len(items): fail("signal count mismatch (run left non-current)")
    for r in runs:
        if r["run_id"] != run_id and r.get("is_current"):
            sbclient.patch("weekly_dashboard_runs", {"is_current": False}, f"?run_id=eq.{r['run_id']}")
    sbclient.patch("weekly_dashboard_runs", {"is_current": True}, f"?run_id=eq.{run_id}")
    check = sbclient.get("v_current_weekly_signals", f"?select=player_key&limit={len(items)+1}")
    if len(check) != len(items): fail("view count mismatch")
    print(f"OK: week {week} current with {len(items)} rows (run {run_id})")
    return 0
if __name__ == "__main__": sys.exit(main())
```

## Output
- The complete revised loader file.
- Bullet list of behavior changes.
- A regression-test sketch: fixture with the 505-row pattern (115 full/stub pairs) asserting 390 keys all resolving to FULL rows; same-content rebuild → NOOP; renamed copy → NOOP (hash match); older week → blocked.
