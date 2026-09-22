"""Weekly chain: odds pull -> snapshot -> compute -> post_queue drafts.

Usage: python3 bin/weekly_chain.py [--week N] [--season 2026] [--skip-pull]

Steps:
  1. Odds pull (collectors/odds_api.snapshot) — quota-guarded, 12h cache.
  2. engine/snapshot_v4.main(week) — freezes vegas_implied (+fantasypros
     ECR-projection) rows into projection_snapshots.
  3. v4/compute_v4.main(week) — signals, single drafts, thread draft.

Prereqs per week (fail closed with a clear message):
  - data/fantasypros/proj_{qb,rb,wr,te}_wk{N}.csv (ECR feed expert
    projections, via the Monday ECR refresh cron's browser pull)
  - data/ecr_pos.json refreshed from the weekly ECR download
    (Monday ECR refresh cron: download CSVs, run bin/refresh_ecr_weekly.py)

The ESPN iPhone projections pipeline was RETIRED 2026-09-12
(scripts removed; ESPN remains only as an injuries/news/scores source).
Only post_queue rows with status='draft' are rotated; approved/posted
rows are never touched.
"""
import argparse
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # weekly_vegas/pipeline root
sys.path.insert(0, BASE)


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

    # ECR feed expert projections (fail-closed): the Monday ECR refresh
    # cron keeps these CSVs current. ESPN's projections pipeline was
    # retired 2026-09-12; ESPN remains only for injuries/news/scores.
    proj_paths = [os.path.join(BASE, "data", "fantasypros",
                               f"proj_{p}_wk{week}.csv")
                  for p in ("qb", "rb", "wr", "te")]
    missing = [p for p in proj_paths if not os.path.exists(p)]
    if missing:
        print(f"BLOCKED: ECR projections CSV(s) missing: {missing}. "
              "Run the Monday ECR refresh (with projections), then rerun.")
        sys.exit(2)
    ecr_path = os.path.join(BASE, "data", "ecr_pos.json")
    if not os.path.exists(ecr_path):
        print(f"BLOCKED: {ecr_path} missing. Refresh ECR first.")
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
