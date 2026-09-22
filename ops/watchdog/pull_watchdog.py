#!/usr/bin/env python3
"""Source-pull watchdog for the trade-value chart pipelines.

Runs AFTER each source's expected pull time and checks, per source:
  (a) ran on schedule — today's runs-log line or a fresh artifact mtime;
  (b) content vintage fresh — from the pull's own meta (vintage/hash), NEVER
      pull time alone; 'source unchanged' (hash-conditional no-op) is healthy,
      'pull failed' is not;
  (c) row counts sane — per-source minimums, zero rows fail closed;
  (d) identity resolution clean — no FAILED/Traceback markers in today's log
      lines, meta n_priced > 0.

Fail-closed audit: a FAILED run must never rewrite the artifact. When today's
log shows FAILED, the artifact mtime must be OLDER than the failed run —
otherwise the failed pull poisoned downstream and that is critical.

Supabase 'landed' check: for each repo-imported source, the newest
data/raw/sources/<source>/*/snapshot-manifest.json is compared against the
pull vintage. Missing manifests degrade to 'pending' (the stage-1 import
stage is still rolling out) — informational, never a failure.

Writes ops/watchdog/health.json (the repo's health surface). Exit 0 when
every source is ok/unchanged; exit 1 on any failed/stale source. Silent
when green: the cron worker reports nothing unless something needs a human.

Usage: python3 ops/watchdog/pull_watchdog.py [--json-only]
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import (GOAL, FS, REPO, today_ct, now_ct, nfl_week, read_json,
                     age_days, todays_run_lines, run_failed_time, CT)

WATCHDIR = os.path.join(REPO, "ops", "watchdog")
HEALTH_OUT = os.path.join(WATCHDIR, "health.json")
HIDDEN = os.path.join(GOAL, "hidden_files")
LOT_HIDDEN = os.path.join(GOAL, "lottery", "hidden_files")
FILES = os.path.join(GOAL, "files")
CACHE = os.path.join(GOAL, "lottery", "data", "sources_cache")
RAW = os.path.join(REPO, "data", "raw", "sources")

REPO_SOURCES = ("espn", "usatoday", "fantasycalc", "fantasypros", "cbs")


def _csv_rows(path):
    try:
        with open(path, newline="") as f:
            return sum(1 for _ in f) - 1
    except OSError:
        return None


def check_daily(cfg, day):
    """Generic daily hash-conditional pull: csv + meta.json + runs log."""
    v = {"expected": cfg["expected"], "label": cfg["label"]}
    log_state, lines = todays_run_lines(cfg["log"], day)
    v["last_run_state"] = log_state
    meta = read_json(cfg["meta"])
    rows = _csv_rows(cfg["csv"])
    v["rows"] = rows
    v["content_vintage"] = (meta or {}).get("vintage") or (meta or {}).get("snapshot_date")
    n_priced = (meta or {}).get("n_priced", (meta or {}).get("n_players"))

    if log_state == "failed":
        v["status"] = "failed"
        v["detail"] = "today's pull run FAILED: %s" % (lines[-1].strip()[:200] if lines else "see log")
    elif log_state in ("ok", "unchanged"):
        v["status"] = "ok" if log_state == "ok" else "unchanged"
        v["detail"] = ("pull ran today, source content unchanged (hash-conditional no-op)"
                       if log_state == "unchanged" else "pull ran today, snapshot updated")
    elif log_state == "did-not-run":
        v["status"] = "stale"
        v["detail"] = "no pull run logged today; artifact age %.1f days" % (age_days(cfg["csv"]) or -1)
    else:
        v["status"] = "stale"
        v["detail"] = "runs log %s (%s)" % (log_state, cfg["log"])

    # (c) row-count sanity — independent of the log verdict.
    if rows is None:
        v["status"], v["detail"] = "failed", "artifact missing: %s" % cfg["csv"]
    elif rows < cfg["min_rows"]:
        v["status"], v["detail"] = "failed", "row count %d below minimum %d" % (rows, cfg["min_rows"])
    if n_priced == 0:
        v["status"], v["detail"] = "failed", "meta n_priced is 0 — pull priced nothing"

    # Fail-closed audit: a failed run must not have rewritten the artifact.
    v["fail_closed"] = None
    if log_state == "failed":
        ft = run_failed_time(cfg["log"], day)
        try:
            art_mtime = datetime.fromtimestamp(os.stat(cfg["csv"]).st_mtime,
                                               timezone.utc)
        except OSError:
            art_mtime = None
        if ft is not None and art_mtime is not None:
            v["fail_closed"] = art_mtime < ft
            if not v["fail_closed"]:
                v["status"] = "failed"
                v["detail"] += " CRITICAL: artifact rewritten AFTER the failed run — downstream poisoned"
    return v


def check_ecr_weekly(day):
    """ECR weekly refresh (browser pull when stale). The pipeline's own
    output is data/ecr_pos.json + the dated proj_*_wkN.csv files."""
    v = {"label": "ECR weekly", "expected": "daily 06:35 CT"}
    p = os.path.join(FS, "data", "ecr_pos.json")
    age = age_days(p)
    v["rows"] = None
    csvs = sorted(glob.glob(os.path.join(FS, "data", "fantasypros", "proj_*_wk*.csv")))
    v["content_vintage"] = os.path.basename(csvs[-1]) if csvs else None
    if age is None:
        v["status"], v["detail"] = "failed", "ecr_pos.json missing"
    elif age < 1.5:
        v["status"], v["detail"] = "ok", "refreshed today (age %.1f days)" % age
    else:
        v["status"], v["detail"] = "stale", "ecr_pos.json age %.1f days — 06:35 refresh did not run" % age
    v["fail_closed"] = None
    return v


def check_fp_season(day):
    """FantasyPros full-season projections snapshot (browser task, Supabase)."""
    v = {"label": "FP season snapshot", "expected": "daily 06:07 CT"}
    dirs = sorted(glob.glob(os.path.join(FS, "data", "fantasypros", "season_snapshots", "20*")))
    if not dirs:
        v["status"], v["detail"] = "failed", "no season_snapshots dirs"
        v["content_vintage"] = None
        v["fail_closed"] = None
        return v
    latest = os.path.basename(dirs[-1])
    v["content_vintage"] = latest
    try:
        vintage_day = datetime.strptime(latest, "%Y-%m-%d").date()
        lag = (day - vintage_day).days
    except ValueError:
        lag = 99
    if lag <= 1:
        v["status"], v["detail"] = "ok", "snapshot %s current" % latest
    else:
        v["status"], v["detail"] = "stale", "latest snapshot %s is %d days old" % (latest, lag)
    v["fail_closed"] = None
    return v


def _article_week(url):
    m = re.search(r"week-(\d+)", url or "")
    return int(m.group(1)) if m else None


def check_weekly_article(cfg, day, week):
    """Weekly article pulls cached as JSON: usatoday.json / cbs.json."""
    v = {"label": cfg["label"], "expected": cfg["expected"]}
    d = read_json(cfg["cache"])
    if not d:
        v.update(status="failed", detail="cache missing: %s" % cfg["cache"],
                 content_vintage=None, fail_closed=None, rows=None)
        return v
    tables = d.get("tables") or []
    v["rows"] = sum(len(t.get("rows", [])) for t in tables)
    url = d.get("url", "")
    art_week = _article_week(url)
    v["content_vintage"] = "week-%d" % art_week if art_week else url
    v["article_url"] = url
    age = age_days(cfg["cache"])
    if len(tables) < 4 or v["rows"] < 50:
        v["status"], v["detail"] = "failed", "only %d tables / %d rows" % (len(tables), v["rows"])
    elif art_week is None:
        v["status"], v["detail"] = "stale", "cannot determine article week from url"
    elif art_week >= week - 1 and (age or 99) <= 8:
        v["status"] = "ok" if art_week == week else "unchanged"
        v["detail"] = ("this week's article cached" if art_week == week
                       else "last week's article cached (this week's not yet published)")
    else:
        v["status"], v["detail"] = "stale", "article is week-%d, current week %d (age %.1f d)" % (
            art_week, week, age or -1)
    v["fail_closed"] = None
    return v


def check_fantasypros_chart(day, week):
    v = {"label": "FP trade chart", "expected": "weekly (article)"}
    p = os.path.join(FILES, "fantasypros_trade_chart.csv")
    rows = _csv_rows(p)
    v["rows"] = rows
    age = age_days(p)
    v["content_vintage"] = "pull %.1f days ago" % age if age is not None else None
    if rows is None:
        v["status"], v["detail"] = "failed", "csv missing"
    elif rows < 150:
        v["status"], v["detail"] = "failed", "only %d rows" % rows
    elif age is not None and age <= 8:
        v["status"], v["detail"] = "ok", "%d rows, refreshed %.1f days ago" % (rows, age)
    else:
        v["status"], v["detail"] = "stale", "csv age %.1f days" % (age or -1)
    v["fail_closed"] = None
    return v


def check_fantasycalc(day, week):
    """FantasyCalc weekly API snapshot. Wednesday cadence: on Wednesdays the
    snapshot must be from this week (<=2 days old); otherwise <=7 days.

    Since 2026-09-16 build_sources_dashboard.py writes per-combo cache files
    fantasycalc_{scoring}_{teams}_qb{qbs}.json (24 combos) and re-stamps the
    fantasycalc_snapshot.json manifest on --refresh-fc. The bare
    fantasycalc_half_12.json is a DEAD legacy file (last written 2026-09-14;
    no pipeline reads it) — it is deliberately never checked.
    Health follows the manifest plus the representative half/12/1QB combo.
    """
    v = {"label": "FantasyCalc", "expected": "weekly (Wednesday)"}
    snap = read_json(os.path.join(CACHE, "fantasycalc_snapshot.json"))
    combo_p = os.path.join(CACHE, "fantasycalc_half_12_qb1.json")
    d = read_json(combo_p)
    combos = (snap or {}).get("combos", [])
    rows = d.get("rows") if isinstance(d, dict) else None
    n_rows = len(rows) if isinstance(rows, list) else None
    missing = [c for c in combos
               if not os.path.exists(os.path.join(CACHE, "fantasycalc_%s.json" % c))]
    age = age_days(combo_p)
    week_label = (snap or {}).get("week")
    v["rows"] = n_rows
    v["n_combos"] = len(combos)
    v["content_vintage"] = (
        "%s snapshot, pull %.1f days ago (API current values)" % (week_label, age)
        if week_label and age is not None else None)
    limit = 2 if day.weekday() == 2 else 7  # Wednesday == 2
    MIN_ROWS = 100  # live representative combo holds ~210 rows
    if snap is None or d is None:
        v["status"], v["detail"] = "failed", "snapshot manifest or half/12/1QB combo cache missing"
    elif not n_rows or n_rows < MIN_ROWS:
        v["status"], v["detail"] = (
            "failed", "representative combo row count %s (min %d)" % (n_rows, MIN_ROWS))
    elif missing:
        v["status"], v["detail"] = (
            "failed", "%d/%d combo cache files missing" % (len(missing), len(combos)))
    elif age is not None and age <= limit:
        v["status"], v["detail"] = (
            "ok", "%s snapshot refreshed %.1f days ago, %d combos" % (week_label, age, len(combos)))
    else:
        v["status"], v["detail"] = "stale", "snapshot age %.1f days (limit %d)" % (age or -1, limit)
    v["fail_closed"] = None
    return v


def refresh_import_health(week):
    """Run the import-stage verifier (make import-health NFL_WEEK=<n>).

    Best-effort: on any failure the watchdog falls back to reading the
    existing output/source-import-health.json, then to 'pending'.
    NFL_WEEK follows the pull scripts' Thursday-flip nfl_week() — passing a
    week whose articles don't exist yet would false-alarm STALE_VINTAGE on
    every source (verified: week-3 CBS slug 404s, no week-3 in the USA Today
    sitemap as of 2026-09-22)."""
    import subprocess as _sp
    try:
        _sp.run(["make", "import-health", "NFL_WEEK=%d" % week], cwd=REPO,
                capture_output=True, timeout=240)
    except Exception:
        pass


IMPORT_HEALTH = os.path.join(REPO, "output", "source-import-health.json")
IMPORT_SCHEMA = "trade-value-import-health-v1"


def supabase_landed(source):
    """Consume the stage-1 consumer contract (docs/import-health-schema.md).

    Returns (landed, status, vintage, imported_at, failure_reason).
    landed is True when the verifier confirms the snapshot's bytes
    (status ok OR stale — staleness is about the source's vintage, not the
    import). 'pending' when the file is missing/wrong-schema (import stage
    still rolling out) — informational, never a failure.
    """
    d = read_json(IMPORT_HEALTH)
    if not d or d.get("schema") != IMPORT_SCHEMA:
        return "pending", None, None, None, "import-health file missing or wrong schema"
    s = (d.get("sources") or {}).get(source)
    if not s:
        return "pending", None, None, None, "source not in import-health"
    landed = s.get("status") in ("ok", "stale")
    return (landed, s.get("status"), s.get("content_vintage"),
            s.get("last_successful_import"), s.get("failure_reason"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json-only", action="store_true")
    args = ap.parse_args()

    day = today_ct()
    week = nfl_week(day)

    cfgs = {
        "prediction_markets": {
            "label": "Prediction markets", "expected": "daily 06:00 CT",
            "csv": os.path.join(FILES, "prediction_markets_season.csv"),
            "meta": os.path.join(HIDDEN, "prediction_markets_meta.json"),
            "log": os.path.join(HIDDEN, "prediction_markets_pull_runs.log"),
            "min_rows": 50},
        "espn": {
            "label": "ESPN projections", "expected": "daily 06:10 CT",
            "csv": os.path.join(FILES, "espn_projections.csv"),
            "meta": os.path.join(HIDDEN, "espn_projections_meta.json"),
            "log": os.path.join(HIDDEN, "espn_projections_runs.log"),
            "min_rows": 400},
        "razzball": {
            "label": "Razzball", "expected": "daily 06:20 CT",
            "csv": os.path.join(FILES, "razzball_projections.csv"),
            "meta": os.path.join(LOT_HIDDEN, "razzball_projections_meta.json"),
            "log": os.path.join(LOT_HIDDEN, "razzball_projections_runs.log"),
            "min_rows": 400},
    }

    sources = {}
    for sid, cfg in cfgs.items():
        sources[sid] = check_daily(cfg, day)
    sources["fp_season"] = check_fp_season(day)
    sources["ecr_weekly"] = check_ecr_weekly(day)
    sources["fantasypros_chart"] = check_fantasypros_chart(day, week)
    sources["fantasycalc"] = check_fantasycalc(day, week)
    sources["usatoday"] = check_weekly_article(
        {"label": "USA Today", "expected": "weekly (article)",
         "cache": os.path.join(CACHE, "usatoday.json")}, day, week)
    sources["cbs"] = check_weekly_article(
        {"label": "CBS", "expected": "weekly (article)",
         "cache": os.path.join(CACHE, "cbs.json")}, day, week)

    # Repo import-stage source names -> watchdog check keys. The repo calls the
    # FantasyPros trade chart "fantasypros"; the watchdog check is
    # "fantasypros_chart" (ECR is a separate, excluded product).
    REPO_TO_CHECK = {"fantasypros": "fantasypros_chart"}
    refresh_import_health(week)
    for sid in REPO_SOURCES:
        landed, sb_status, vintage, imported_at, failure = supabase_landed(sid)
        key = REPO_TO_CHECK.get(sid, sid)
        s = sources.get(key)
        if s is None:
            continue
        s["supabase_landed"] = landed
        s["supabase_status"] = sb_status
        s["supabase_vintage"] = vintage
        s["supabase_imported_at"] = imported_at
        s["supabase_failure"] = failure

    bad = {k: v for k, v in sources.items() if v.get("status") in ("failed", "stale")}
    health = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generated_at_ct": now_ct().isoformat(),
        "nfl_week": week,
        "sources": sources,
        "summary": {
            "ok": sum(1 for v in sources.values() if v.get("status") in ("ok", "unchanged")),
            "failed": [k for k, v in sources.items() if v.get("status") == "failed"],
            "stale": [k for k, v in sources.items() if v.get("status") == "stale"],
        },
    }
    os.makedirs(WATCHDIR, exist_ok=True)
    with open(HEALTH_OUT, "w") as f:
        json.dump(health, f, indent=1)

    if not args.json_only:
        for sid, v in sources.items():
            print("%-18s %-9s %s" % (sid, v.get("status"),
                                     v.get("detail", "")[:90]))
        sb = [k for k, v in sources.items() if v.get("supabase_landed") == "pending"]
        if sb:
            print("supabase import pending for: %s" % ", ".join(sb))
        print("wrote", HEALTH_OUT)

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
