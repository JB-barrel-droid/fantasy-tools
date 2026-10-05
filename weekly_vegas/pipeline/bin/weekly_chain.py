"""Weekly chain: odds pull -> snapshot -> compute -> post_queue drafts.

Usage: python3 bin/weekly_chain.py [--week N] [--season 2026] [--skip-pull]

Steps:
  1. Odds pull (collectors/odds_api.snapshot) — quota-guarded, 12h cache.
  2. engine/snapshot_v4.main(week) — freezes vegas_implied (+ ESPN ROS
      expert-projection) rows into projection_snapshots.
  3. v4/compute_v4.main(week) — signals, single drafts, thread draft.

Prereqs per week (fail closed with a clear message):
  - output/espn_pull/files/espn_weekly_projections.csv (repo root) with
    ESPN's expert-leg projections (Mike Clay model, rest-of-season).
    Produced by pipelines/pull_espn_projections.py. The gate checks two
    layers: the file exists, and its espn_snapshot_date content vintage
    is within ESPN_MAX_AGE_DAYS (a byte-identical re-pull does not reset
    the clock — freshness measures when ESPN moved its numbers, never
    when we downloaded them). The prior ECR expert-leg input was retired
    (JEG-399 / JEG-ECR-EXIT 2026-10-05).

Only post_queue rows with status='draft' are rotated; approved/posted
rows are never touched.
"""
import argparse
import csv
import os
import sys
from datetime import date

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
REPO = os.path.dirname(BASE)  # repo root: output/espn_pull lives here
sys.path.insert(0, BASE)

ESPN_WEEKLY_CSV = os.path.join(
    REPO, "output", "espn_pull", "files", "espn_weekly_projections.csv")
ESPN_MAX_AGE_DAYS = 3  # mirrors the game-day ESPN gate (JEG-418)


def _espn_snapshot_date(csv_path):
    """Latest espn_snapshot_date in the CSV, or None when unreadable."""
    try:
        with open(csv_path, newline="") as f:
            dates = [r.get("espn_snapshot_date") for r in csv.DictReader(f)]
        dates = [d for d in dates if d]
        return max(dates) if dates else None
    except Exception:
        return None


def check_espn_gate(csv_path=None, today=None):
    """Fail-closed expert-leg gate. Returns (ok, message).

    Layer 1: the ESPN weekly projections file exists.
    Layer 2: its espn_snapshot_date content vintage is within
    ESPN_MAX_AGE_DAYS. A re-pull of unchanged content does not reset
    the vintage clock.
    """
    csv_path = csv_path or ESPN_WEEKLY_CSV
    today = today or str(date.today())
    if not os.path.exists(csv_path):
        return (False,
                f"BLOCKED: {csv_path} missing. Run "
                "pipelines/pull_espn_projections.py to pull ESPN expert "
                "projections, then rerun.")
    snap = _espn_snapshot_date(csv_path)
    if not snap:
        return (False,
                f"BLOCKED: {csv_path} has no espn_snapshot_date; "
                "expert-leg vintage is unverifiable.")
    try:
        age = (date.fromisoformat(today) - date.fromisoformat(snap[:10])).days
    except ValueError:
        return (False,
                f"BLOCKED: unparseable espn_snapshot_date {snap!r} in "
                f"{csv_path}.")
    if age > ESPN_MAX_AGE_DAYS:
        return (False,
                f"BLOCKED: ESPN expert projections are {age}d old "
                f"(snapshot {snap[:10]}, max {ESPN_MAX_AGE_DAYS}d). Refresh "
                "via pipelines/pull_espn_projections.py.")
    return (True, f"ESPN expert leg OK (snapshot {snap[:10]}, {age}d old).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--skip-pull", action="store_true",
                    help="skip the odds pull (use latest props already in DB)")
    a = ap.parse_args()

    from engine.week import current_week
    week = a.week or current_week(a.season)
    print(f"=== weekly chain: season {a.season} week {week} ===", flush=True)

    # ESPN expert-leg gate (fail-closed, JEG-419): the ECR feed was retired
    # (JEG-399 / JEG-ECR-EXIT). Block loudly when the ESPN expert leg is
    # missing or its content vintage is stale.
    ok, msg = check_espn_gate()
    print(msg, flush=True)
    if not ok:
        sys.exit(2)

    if not a.skip_pull:
        sys.path.insert(0, os.path.join(BASE, "collectors"))
        import odds_api
        n, remaining = odds_api.snapshot()
        print(f"odds pull: {n} rows written, quota remaining: {remaining}",
              flush=True)
    else:
        print("skipping odds pull (--skip-pull)", flush=True)

    # FDS fallback pull (2026-09-17): free, keyless, quota-free. Best-effort:
    # a failed FDS pull never blocks the chain — compute/snapshot simply
    # run local-only. The collector itself is fail-closed (no partial file).
    if not a.skip_pull:
        try:
            import subprocess
            r = subprocess.run(
                [sys.executable,
                 os.path.join(BASE, "collectors", "fds_weekly.py"),
                 "--week", str(week)],
                capture_output=True, text=True, timeout=120)
            print((r.stdout or "").strip(), flush=True)
            if r.returncode != 0:
                print(f"WARNING: FDS pull failed (local-only build): "
                      f"{(r.stderr or '')[-300:]}", flush=True)
        except Exception as e:
            print(f"WARNING: FDS pull error (local-only build): {e}",
                  flush=True)

    # enrichment: sleeper crosswalk/injuries/trending + espn (best effort)
    sys.path.insert(0, os.path.join(BASE, "loaders"))
    try:
        import sleeper as sleeper_loader
        st = sleeper_loader.current_state()
        print(f"sleeper state: season {st['season']} week {st['week']}",
              flush=True)
        pl = sleeper_loader.players_cache()
        print(f"sleeper crosswalk: {sleeper_loader.load_crosswalk(pl)}",
              flush=True)
        print(f"sleeper injuries: {sleeper_loader.load_injuries(pl)}",
              flush=True)
        print(f"sleeper trending: {sleeper_loader.load_trending()}",
              flush=True)
    except Exception as e:
        print(f"WARNING: sleeper enrichment failed: {e}", flush=True)
    try:
        import espn as espn_loader
        print(f"espn injuries: {espn_loader.load_injuries()}", flush=True)
        print(f"espn scoreboard: {espn_loader.load_scoreboard()}",
              flush=True)
    except Exception as e:
        # ESPN public API is Akamai-blocked from our egress (2026-09-11);
        # sleeper covers injuries meanwhile. Non-fatal.
        print(f"WARNING: espn enrichment failed (known egress block): {e}",
              flush=True)
    try:
        import weather as weather_loader
        print(f"weather: {weather_loader.main()}", flush=True)
    except Exception as e:
        print(f"WARNING: weather enrichment failed: {e}", flush=True)
    try:
        import dfs_salaries as dk_loader
        print(f"dk salaries: {dk_loader.main(week=week)}", flush=True)
    except Exception as e:
        print(f"WARNING: dk salary load failed: {e}", flush=True)
    try:
        import news as news_loader
        print(f"news: {news_loader.main(week=week)}", flush=True)
    except Exception as e:
        print(f"WARNING: news load failed: {e}", flush=True)
    try:
        from salary_signals import main as salary_sig
        salary_sig(week=week)
    except Exception as e:
        print(f"WARNING: salary signals failed: {e}", flush=True)
    try:
        from build_ecr_files import main as build_ecr
        build_ecr()
    except Exception as e:
        print(f"WARNING: ecr file build failed: {e}", flush=True)

    from engine.snapshot_v4 import main as snapshot_main
    snapshot_main(week=week, season=a.season)

    from v4.compute_v4 import main as compute_main
    compute_main(week=week, season=a.season)

    print("=== weekly chain complete ===", flush=True)


if __name__ == "__main__":
    main()
