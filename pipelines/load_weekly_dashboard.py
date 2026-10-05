#!/usr/bin/env python3
"""Load the canonical weekly signals bundle into the Supabase weekly dashboard tables.

Determinism guarantees (JEG-394):
- Bundle selection: explicit path (CLI/env) preferred; mtime fallback is
  local-only and refused in CI. Bundle meta (season/week/built_at) validated
  fail-closed; optional EXPECTED_WEEK cross-check.
- Dedupe: explicit FULL (non-null vegas_leg) / STUB classification. One FULL
  row per normalized player_key; two FULL rows or an unrecognized duplicate
  shape blocks the run. No heuristic scoring.
- Idempotency: keyed on (season, week, bundle_sha256) of the current run.
  Older season/week or older built_at blocked unless --allow-rollback.
- Promotion: atomic via the public.promote_weekly_dashboard_run RPC (JEG-393)
  — no zero/two-current window, idempotent on retry.

Usage:
    python3 pipelines/load_weekly_dashboard.py [--bundle PATH] [--expected-week N] [--allow-rollback]
    WEEKLY_BUNDLE_PATH=/path/to/bundle.json python3 pipelines/load_weekly_dashboard.py
Exit codes: 0 ok / no-op, 2 blocked (missing input or verification failure).
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from datetime import date

# Supabase client: the vault-backed skill on the Muse VM; in GitHub Actions
# the gh_sbclient shim is placed on PYTHONPATH as `sbclient` (same interface).
SKILL_BIN = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
if os.path.isdir(SKILL_BIN):
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


def resolve_bundle(explicit=None, require_explicit=False):
    if explicit:
        if not os.path.isfile(explicit):
            fail(f"bundle not found: {explicit}")
        return explicit
    env_path = os.environ.get("WEEKLY_BUNDLE_PATH")
    if env_path:
        if not os.path.isfile(env_path):
            fail(f"WEEKLY_BUNDLE_PATH not found: {env_path}")
        return env_path
    if require_explicit:
        fail("CI requires an explicit bundle via --bundle or WEEKLY_BUNDLE_PATH")
    files = sorted(glob.glob(BUNDLE_GLOB), key=os.path.getmtime)
    if not files:
        fail("no staged weekly signals bundle found under weekly_dashboard_refresh_*/")
    return files[-1]  # local convenience only; never used in CI


def load_bundle(path):
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"bundle {path} is not valid JSON: {e}")
    meta = bundle.get("meta")
    if not isinstance(meta, dict):
        fail(f"bundle {path} missing meta object")
    week = meta.get("week")
    season = meta.get("season")
    built_at = meta.get("built_at")
    if not isinstance(week, int) or week < 1 or week > 25:
        fail(f"bundle {path} meta.week missing or not a sane week int: {week!r}")
    if not isinstance(season, int) or season < 2020 or season > 2100:
        fail(f"bundle {path} meta.season missing or not a sane season int: {season!r}")
    if not built_at or not isinstance(built_at, str):
        fail(f"bundle {path} meta.built_at missing")
    if not isinstance(bundle.get("players"), list) or not bundle["players"]:
        fail(f"bundle {path} has no players")
    return bundle, meta, sha


def classify(row):
    """FULL iff the row carries a non-null vegas_leg; STUB iff it is a
    no_market_read stub (the engine omits vegas_leg on stubs entirely).
    Anything else is an unrecognized shape."""
    if row.get("vegas_leg") is not None:
        return "FULL"
    if row.get("category") == "no_market_read":
        return "STUB"
    return None


def dedupe(players):
    """Per normalized player_key keep the FULL row when present, else the lone
    STUB (e.g. dallas goedert, week 4: stub-only, still the player's signal).
    Fail closed on duplicate FULL rows, duplicate STUBs, missing keys, or
    unrecognized row shapes."""
    best = {}
    for idx, row in enumerate(players):
        if not isinstance(row, dict):
            fail(f"player row {idx} is not an object")
        key = (row.get("player_key") or "").strip().lower()
        if not key:
            fail(f"player row {idx} missing player_key")
        shape = classify(row)
        if shape is None:
            fail(f"player {key}: unrecognized row shape "
                 f"(no vegas_leg and category={row.get('category')!r})")
        prior = best.get(key)
        if prior is None:
            best[key] = (shape, row)
            continue
        if shape == "FULL" and prior[0] == "FULL":
            fail(f"player {key}: two FULL rows in bundle")
        if shape == "STUB" and prior[0] == "STUB":
            fail(f"player {key}: two STUB rows in bundle")
        if shape == "FULL":
            best[key] = (shape, row)  # FULL beats STUB
        # lone STUB already kept; a second row here is always an error above
    return {k: v[1] for k, v in best.items()}


def manifest_built_at(m):
    return (m or {}).get("bundle_built_at") or (m or {}).get("built_at")


# JEG-404: the dashboard publishes only ESPN-sourced expert numbers that are
# fresh on CONTENT VINTAGE (espn_snapshot_date = when ESPN last changed the
# numbers), never pull time. A byte-identical re-pull resets nothing.
ESPN_EXPERT_SOURCE = "espn_ros"
ESPN_VINTAGE_MAX_AGE_DAYS = 3


def expert_vintage_block_reason(meta, rows, today=None):
    """Source-content-vintage gate (JEG-404). Returns a BLOCKED reason string
    if the bundle's expert leg must not be promoted, else None.

    Fail-closed on: expert_source missing or != espn_ros, absent /
    non-unanimous / unparseable espn_snapshot_date, or vintage older than
    ESPN_VINTAGE_MAX_AGE_DAYS (consistent with the game-day ESPN 3-day gate).
    """
    source = (meta.get("expert_source") or "").strip()
    if source != ESPN_EXPERT_SOURCE:
        return (f"bundle expert_source is {source!r}, expected "
                f"{ESPN_EXPERT_SOURCE!r}")
    dates = set()
    for key, row in rows.items():
        d = (row.get("espn_snapshot_date") or "")
        if not str(d).strip():
            return f"player {key} has no espn_snapshot_date"
        dates.add(str(d).strip())
    if len(dates) > 1:
        return f"espn_snapshot_date not unanimous across rows: {sorted(dates)}"
    vintage = dates.pop()
    try:
        snap = date.fromisoformat(vintage)
    except ValueError:
        return f"espn_snapshot_date {vintage!r} is not an ISO date"
    today = today or date.today()
    age = (today - snap).days
    if age > ESPN_VINTAGE_MAX_AGE_DAYS:
        return (f"ESPN content vintage {vintage} is {age} days old "
                f"(max {ESPN_VINTAGE_MAX_AGE_DAYS})")
    return None


def promote(run_id, expected_signals):
    """Atomic promotion via the JEG-393 RPC. Idempotent: safe to retry."""
    try:
        sbclient.rpc("promote_weekly_dashboard_run",
                     {"p_run_id": run_id, "p_expected_signals": expected_signals})
    except Exception as e:
        fail(f"promote_weekly_dashboard_run failed for {run_id}: {e}")


def abandon_run(run_id):
    """Best-effort cleanup of a run this loader created but never promoted.
    Only ever touches the given run_id; never masks the original error."""
    try:
        sbclient.delete("weekly_dashboard_signals", f"?run_id=eq.{run_id}")
    except Exception as e:
        print(f"warning: could not delete orphan signals for {run_id}: {e}", file=sys.stderr)
    try:
        sbclient.delete("weekly_dashboard_runs", f"?run_id=eq.{run_id}")
    except Exception as e:
        print(f"warning: could not delete orphan run {run_id}: {e}", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load the weekly signals bundle into Supabase.")
    ap.add_argument("--bundle", default=None,
                    help="Explicit bundle path (default: WEEKLY_BUNDLE_PATH env, else newest VM bundle).")
    ap.add_argument("--expected-week", type=int, default=None,
                    help="Refuse to publish if bundle week differs.")
    ap.add_argument("--allow-rollback", action="store_true",
                    help="Permit publishing an older (season, week, built_at); audited in manifest.")
    args = ap.parse_args(argv)

    in_ci = os.environ.get("CI") == "true" or bool(os.environ.get("GITHUB_ACTIONS"))
    bundle_path = resolve_bundle(args.bundle, require_explicit=in_ci)
    bundle, meta, bundle_sha = load_bundle(bundle_path)
    week = meta["week"]
    season = meta["season"]
    built_at = meta["built_at"]

    expected_week = args.expected_week
    if expected_week is None and os.environ.get("EXPECTED_WEEK"):
        try:
            expected_week = int(os.environ["EXPECTED_WEEK"])
        except ValueError:
            fail(f"EXPECTED_WEEK not an int: {os.environ['EXPECTED_WEEK']!r}")
    if expected_week is not None and week != expected_week:
        fail(f"bundle week {week} != expected week {expected_week}")

    rows = dedupe(bundle["players"])
    if not rows:
        fail("dedupe produced zero rows")

    manifest = {
        "engine": "v4",
        "loader": "pipelines/load_weekly_dashboard.py",
        "bundle": os.path.basename(bundle_path),
        "bundle_path": bundle_path,
        "bundle_sha256": bundle_sha,
        "season": season,
        "week": week,
        "bundle_built_at": built_at,
        "bundle_source_file": meta.get("source_file"),
        "n_bundle_players": len(bundle["players"]),
        "n_deduped": len(rows),
    }
    if args.allow_rollback:
        manifest["allow_rollback"] = True

    # Idempotency: the CURRENT run for this (season, week) already covers this
    # exact bundle bytes => NOOP. A renamed copy with identical bytes NOOPs;
    # same metadata with changed contents loads a new run.
    current = sbclient.get(
        "weekly_dashboard_runs",
        "?select=run_id,week,season,is_current,source_manifest"
        "&is_current=eq.true"
        f"&season=eq.{season}&week=eq.{week}",
    )
    for r in current:
        m = r.get("source_manifest") or {}
        if m.get("bundle_sha256") == bundle_sha and manifest_built_at(m) == built_at:
            print(f"NOOP: season {season} week {week} bundle sha {bundle_sha[:12]} "
                  f"already current (run {r['run_id']})")
            return 0

    if not args.allow_rollback:
        # Refuse to publish behind the current (season, week), or behind the
        # current week's bundle build time.
        all_current = sbclient.get(
            "weekly_dashboard_runs",
            "?select=run_id,season,week,source_manifest&is_current=eq.true",
        )
        for r in all_current:
            r_season = r.get("season", 2026)
            r_week = r.get("week", 0)
            if (r_season, r_week) > (season, week):
                fail(f"refusing rollback: current run {r['run_id']} is "
                     f"season {r_season} week {r_week}; pass --allow-rollback to override")
            cur_built = manifest_built_at(r.get("source_manifest"))
            if (r_season, r_week) == (season, week) and cur_built and cur_built > built_at:
                fail(f"refusing rollback: current run {r['run_id']} for week {week} "
                f"has newer bundle_built_at {cur_built} > {built_at}; "
                f"pass --allow-rollback to override")

    # Source-content-vintage gate (JEG-404). Deliberately placed AFTER the
    # NOOP check: a bundle already current with identical bytes must stay a
    # clean no-op (nothing new is published), while any bundle that would
    # actually be promoted must carry fresh ESPN expert numbers.
    block = expert_vintage_block_reason(meta, rows)
    if block:
        fail(f"vintage gate: {block} (bundle {bundle_path})")
    manifest["expert_source"] = meta.get("expert_source")
    manifest["espn_vintage"] = sorted({
        str(r.get("espn_snapshot_date")).strip() for r in rows.values()
    })[-1]

    run_rows = sbclient.post(
        "weekly_dashboard_runs",
        {"week": week, "season": season, "source_manifest": manifest, "is_current": False},
    )
    run_id = run_rows[0]["run_id"]
    print(f"run {run_id} created for week {week} ({len(rows)} players)")

    # Anything that fails before promote() commits leaves an orphan run behind.
    # Clean up our own unpromoted run so partial-signal orphans never accumulate.
    # Once promote() succeeds the run is live and must NOT be auto-deleted.
    promoted = False
    try:
        n = _insert_and_promote(run_id, rows)
        promoted = True
    except SystemExit:
        if not promoted:
            abandon_run(run_id)
        raise
    except Exception as e:  # pragma: no cover - defensive
        if not promoted:
            abandon_run(run_id)
        fail(f"unexpected error during load of run {run_id}: {e}")

    # Post-promotion consistency check: the run is live now; a failure here
    # is investigated, never auto-cleaned.
    check = sbclient.get(
        "v_current_weekly_signals",
        f"?select=player_key&season=eq.{season}&week=eq.{week}&limit={n + 1}",
    )
    if len(check) != n:
        fail(f"view count mismatch: expected {n}, view returned {len(check)}")
    print(f"OK: season {season} week {week} current with {n} rows "
          f"(run {run_id}, bundle sha {bundle_sha[:12]})")
    return 0


def _insert_and_promote(run_id, rows):
    """Insert signals, verify, promote. Returns the signal count.
    Raises SystemExit (via fail) on any problem; the caller abandons the
    run only if promotion never committed."""
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

    # Read-back verification before promotion; the verified count is passed to
    # the RPC for a second, in-transaction check.
    got = sbclient.get(
        "weekly_dashboard_signals",
        f"?select=player_key&run_id=eq.{run_id}&limit={len(items) + 1}",
    )
    if len(got) != len(items):
        fail(
            f"signal count mismatch: wrote {len(items)}, read back {len(got)} "
            f"(run {run_id} left non-current)"
        )

    promote(run_id, len(items))
    return len(items)


if __name__ == "__main__":
    sys.exit(main())
