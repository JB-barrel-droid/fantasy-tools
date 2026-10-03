#!/usr/bin/env python3
"""Build pipeline-checkpoints.json: 9 explicit checkpoints per source with real timestamps.

Reads actual artifacts from disk (no inference from value counts):
  C1 Publication/discovery  - publisher release (from pull file URL/date)
  C2 Raw collection         - pull file fetched_at (ops/watchdog/pulls/)
  C3 Supabase landing       - db_latest_arrived_at (health file)
  C4 Snapshot/manifest      - snapshot_path mtime (data/raw/sources/)
  C5 Health verification    - checked_at + status (health file)
  C6 Candidate build/review - candidate dir mtime + review file (output/comparison-candidates/, output/comparison-review/)
  C7 Fixture promotion      - promotion file promoted_at + review_verdict (output/comparison-promotions/)
  C8 Sync/validation        - fixture built_at vs dist copy mtime
  C9 Deployment/live        - (browser checks GitHub Actions API live)

Output: output/pipeline-checkpoints.json (also synced to dist/modules/ by cron)

Each checkpoint: {label, what, timestamp, status, reason}
Status: ok/warn/bad/unk with specific reason. Never green on stale data.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
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



def expected_content_week(today=None):
    """Canonical expected NFL content week for rendered-output checks.

    Delegates to pipelines/nfl_week.py::current_nfl_week (content week turns
    over on Tuesday, after Monday night). A naive days-since-kickoff count
    (e.g. (now - 2026-09-03).days // 7 + 1) flips a week early at Thursday
    00:00 UTC and false-reds every source's C10 rendered check -- observed
    2026-09-30 when it computed Week 5 while the pipeline's canonical week
    (and the live data) was Week 4.
    """
    sys.path.insert(0, str(REPO / "pipelines"))
    from nfl_week import current_nfl_week

    return current_nfl_week(today)

CHECKPOINTS = [
    ("c1_publication", "C1 · Publication/discovery",
     "Publisher releases new trade-value data (article/chart update)"),
    ("c2_collection", "C2 · Raw collection",
     "Pull script fetches publisher HTML → ops/watchdog/pulls/*.json"),
    ("c3_supabase", "C3 · Supabase landing",
     "Save script writes rows to Supabase (public.source_trade_values etc.)"),
    ("c4_snapshot", "C4 · Snapshot/manifest",
     "import_supabase_references.py stamps Supabase → data/raw/sources/ (Supabase → repo, not reverse)"),
    ("c5_health", "C5 · Health verification",
     "verify_import_health.py checks integrity → output/source-import-health.json"),
    ("c6_candidate", "C6 · Candidate build/review",
     "build_comparison_source_section.py builds candidate → review_comparison_candidate.py reviews"),
    ("c7_promotion", "C7 · Fixture promotion",
     "promote_comparison_section.py promotes reviewed candidate → fixture (only on genuine 'ready' verdict)"),
    ("c8_sync", "C8 · Sync/validation",
     "Fixture synced app/ → dist/, validation gates run"),
    ("c9_deploy", "C9 · Deployment/live artifact",
     "GitHub Pages deploys dist/ (browser checks Actions API live)"),
    ("c10_rendered", "C10 · Rendered production output",
     "Live production JSON serves correct week labels and loadable comparison data (catches label/data drift the pipes miss)"),
]


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def parse_iso(s):
    if not s:
        return None
    try:
        # Handle date-only like "2026-09-29"
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return datetime.fromisoformat(s + "T00:00:00+00:00")
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def days_old(iso_str):
    dt = parse_iso(iso_str)
    if not dt:
        return None
    delta = datetime.now(timezone.utc) - dt
    return delta.total_seconds() / 86400


def evaluate_pages_deploy(runs):
    """Classify GitHub Pages deploy health from recent workflow runs.

    An in_progress/queued run is NOT a failure signal: the verdict is judged
    from the most recent COMPLETED run instead. Rationale: every push triggers
    a deploy, so "latest run in progress" is the normal steady state of the
    30-min health cron; flagging it bad reds the monitor on every push cycle
    (observed 2026-10-01 08:38 UTC: a healthy in-flight deploy from the routine
    03:37 CDT health push was reported bad). A failed completed deploy stays
    bad; a stale (>2d) successful deploy warns.

    A "cancelled" conclusion on a run that has a NEWER run ahead of it in the
    list is a push-race supersede (GitHub cancels the older in-flight run when
    a new push arrives), not a deploy failure -- observed 2026-10-03 14:42 UTC
    when the checkpoint rebuild judged a superseded cancel bad while the
    newer push's deploy was still in flight. Such runs are skipped before
    judging. A cancelled run with nothing newer is still bad: the newest
    deploy never succeeded.
    """
    def verdict(run):
        run_status = run.get("status")
        run_conclusion = run.get("conclusion")
        run_updated = run.get("updated_at")
        run_days = days_old(run_updated)
        if run_status != "completed" or run_conclusion != "success":
            return {"timestamp": run_updated, "status": "bad",
                    "reason": f"Last Pages deploy: {run_status}/{run_conclusion}. Deploy may have failed."}
        if run_days is not None and run_days > 2:
            return {"timestamp": run_updated, "status": "warn",
                    "reason": f"Last successful Pages deploy {run_days:.1f}d ago. Content may be stale."}
        return {"timestamp": run_updated, "status": "ok",
                "reason": f"Pages deployed successfully {(run_days or 0):.1f}d ago."}

    # runs arrive newest-first. Drop superseded cancels before judging.
    judged = [r for i, r in enumerate(runs)
              if not (i > 0 and r.get("status") == "completed"
                      and r.get("conclusion") == "cancelled")]
    completed = [r for r in judged if r.get("status") == "completed"]
    if completed:
        latest = completed[0]
        v = verdict(latest)
        if v["status"] == "ok":
            in_flight = [r for r in runs if r.get("status") in ("in_progress", "queued")]
            if in_flight:
                v = {"timestamp": in_flight[0].get("updated_at"), "status": "ok",
                     "reason": ("Deploy in progress; last completed deploy succeeded "
                                f"{(days_old(latest.get('updated_at')) or 0):.1f}d ago.")}
        return v
    if runs:
        r = runs[0]
        return {"timestamp": r.get("updated_at"), "status": "unk",
                "reason": (f"Latest Pages run is {r.get('status')}/{r.get('conclusion')}; "
                           "no completed run to judge yet.")}
    return {"timestamp": None, "status": "unk",
            "reason": "No Pages deploy runs found."}


def newest_file_mtime(pattern_dir, pattern):
    """Find newest file matching pattern in dir, return (path, mtime_iso)."""
    d = REPO / pattern_dir
    if not d.is_dir():
        return None, None
    best = None
    best_mtime = 0
    for f in d.iterdir():
        if re.match(pattern, f.name) and f.is_file():
            mtime = f.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best = f
    if best:
        return str(best.relative_to(REPO)), datetime.fromtimestamp(best_mtime, tz=timezone.utc).isoformat()
    return None, None


def newest_dir_mtime(parent_dir):
    """Find newest subdirectory, return (name, mtime_iso)."""
    d = REPO / parent_dir
    if not d.is_dir():
        return None, None
    best = None
    best_mtime = 0
    for sub in d.iterdir():
        if sub.is_dir():
            mtime = sub.stat().st_mtime
            if mtime > best_mtime:
                best_mtime = mtime
                best = sub
    if best:
        return best.name, datetime.fromtimestamp(best_mtime, tz=timezone.utc).isoformat()
    return None, None


def newest_razzball_leg():
    """Return the freshest committed Razzball DDF leg.

    Razzball is not a Supabase/import-health source by project rule. Its
    monitor provenance comes from the DDF leg built from the raw Razzball
    snapshot, which records the raw snapshot date, row count, and hash.
    """
    leg_dir = REPO / "data" / "ddf-two-tier"
    candidates = []
    if not leg_dir.is_dir():
        return None, None
    scoring_rank = {"ppr": 3, "half_ppr": 2, "standard": 1}
    for leg_path in leg_dir.glob("*/ddf_leg_razzball.json"):
        try:
            leg = json.loads(leg_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        inputs = leg.get("inputs", {})
        vintage = inputs.get("razzball_snapshot_date") or ""
        generated = leg.get("generated_at") or ""
        teams_rank = 1 if inputs.get("teams") == 12 else 0
        score_rank = scoring_rank.get(inputs.get("scoring"), 0)
        candidates.append((vintage, generated, teams_rank, score_rank, leg_path, leg))
    if not candidates:
        return None, None
    candidates.sort(reverse=True)
    _, _, _, _, leg_path, leg = candidates[0]
    return str(leg_path.relative_to(REPO)), leg


def razzball_health_from_fixture(fixture):
    """Synthesize monitor health for Razzball from fixture + DDF leg metadata.

    This is intentionally separate from source-import-health: Razzball is a
    hard-excluded import source, so a green monitor row must prove the committed
    DDF lineage is present instead of inventing a Supabase landing.
    """
    src_data = fixture.get("sources", {}).get("razzball", {})
    leg_path, leg = newest_razzball_leg()
    inputs = (leg or {}).get("inputs", {})
    combos = src_data.get("combos", {})
    validation = fixture.get("source_validation", {}).get("razzball")
    vintage = (
        inputs.get("razzball_snapshot_date")
        or src_data.get("vintage")
        or src_data.get("week_designated")
    )
    generated_at = (leg or {}).get("generated_at") or fixture.get("built_at")
    rows = inputs.get("razzball_snapshot_rows")
    ok = bool(leg_path and combos and validation == "live")
    return {
        "status": "ok" if ok else "missing",
        "failure_reason": None if ok else "Missing live Razzball fixture section or DDF leg.",
        "content_vintage": vintage,
        "snapshot_path": leg_path,
        "db_latest_arrived_at": None,
        "db_latest_rows": None,
        "db_latest_vintage": vintage,
        "row_count": rows,
        "supabase_landing": False,
        "supabase_table": None,
        "last_successful_import": generated_at,
        "_checked_at": generated_at,
        "_lineage": "fixture + DDF leg",
        "_raw_snapshot_path": inputs.get("razzball_snapshot"),
        "_raw_snapshot_sha256": inputs.get("razzball_snapshot_sha256"),
    }


def build_checkpoints():
    # Load health file: freshest valid input wins. The gitignored output/
    # runtime file only exists on the machine that ran the health gate; a
    # manual rebuild elsewhere (clean worktree, CI) must resolve to the
    # freshest committed copy instead of silently producing "unk" checkpoints
    # from an absent file. Same rule as sync_dashboard_artifacts.py's
    # import_health_source (2026-10-01): never a hardcoded fallback.
    from sync_dashboard_artifacts import import_health_source
    health_path = import_health_source(REPO)
    health = {}
    health_checked_at = None
    if health_path.exists():
        with open(health_path) as f:
            health = json.load(f)
        health_checked_at = health.get("checked_at")

    # Load fixture
    fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    fixture = {}
    fixture_built_at = None
    if fixture_path.exists():
        with open(fixture_path) as f:
            fixture = json.load(f)
        fixture_built_at = fixture.get("built_at")

    # Load chain status
    chain_path = REPO / "output" / "comparison-chain-status.json"
    chain = {}
    if chain_path.exists():
        with open(chain_path) as f:
            chain = json.load(f)
    chain_run_at = chain.get("run_at")
    chain_runner = chain.get("runner", "unknown")
    chain_success = chain.get("success", False)
    chain_sources = chain.get("sources", {})

    # Dist fixture mtime (sync checkpoint)
    dist_fixture = REPO / "dist" / "modules" / "comparison-sources-data.json"
    dist_mtime = None
    if dist_fixture.exists():
        dist_mtime = datetime.fromtimestamp(dist_fixture.stat().st_mtime, tz=timezone.utc).isoformat()

    result = {
        "generated_at": iso_now(),
        "schema": "pipeline-checkpoints-v1",
        "nfl_week": health.get("nfl_week"),
        "checkpoints": [{"key": k, "label": label, "what": what} for k, label, what in CHECKPOINTS],
        "sources": {},
    }

    # Fetch GitHub Pages deploy status ONCE (not per-source) to avoid rate limits
    pages_deploy = {"status": "unk", "timestamp": None, "reason": "Deploy status check not yet implemented in Python; browser checks Actions API live."}
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/repos/JB-barrel-droid/fantasy-tools/actions/workflows/pages.yml/runs?per_page=5",
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "fantasy-tools-monitor"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        runs = data.get("workflow_runs", [])
        pages_deploy = evaluate_pages_deploy(runs)
    except Exception as e:
        pages_deploy = {"timestamp": None, "status": "unk",
            "reason": f"Could not check Pages API: {str(e)[:60]}. Browser checks live."}

    for src in SOURCES:
        h = health.get("sources", {}).get(src, {})
        if src == "razzball":
            h = razzball_health_from_fixture(fixture)
        cps = {}

        # C1: Publication/discovery - from content_vintage (when publisher released)
        c1_ts = h.get("content_vintage")
        # content_vintage may be a date or "Week N"; try to parse
        c1_days = days_old(c1_ts)
        if c1_days is None and c1_ts:
            # Handle "Week N" format: compare to current NFL week
            m = re.match(r"Week\s+(\d+)", str(c1_ts), re.IGNORECASE)
            if m:
                current_week = health.get("nfl_week")
                try:
                    vintage_week = int(m.group(1))
                    current_week = int(current_week) if current_week else None
                    if current_week and vintage_week <= current_week:
                        # Assume ~7 days per week; current week = 0 days old
                        c1_days = (current_week - vintage_week) * 7.0
                except (ValueError, TypeError):
                    pass
        if c1_ts and c1_days is not None:
            if c1_days > 14:
                cps["c1_publication"] = {"timestamp": c1_ts, "status": "bad",
                    "reason": f"Publisher data is {c1_days:.0f} days old ({c1_ts}). No new release detected."}
            elif c1_days > 7:
                cps["c1_publication"] = {"timestamp": c1_ts, "status": "warn",
                    "reason": f"Publisher data is {c1_days:.0f} days old. Awaiting new release (normal for weekly cadence)."}
            else:
                cps["c1_publication"] = {"timestamp": c1_ts, "status": "ok",
                    "reason": f"Publisher released {c1_ts} ({c1_days:.1f}d ago)."}
        else:
            cps["c1_publication"] = {"timestamp": c1_ts, "status": "unk",
                "reason": "No publisher vintage recorded in health file."}

        # C2: Raw collection - from pull file or health snapshot_path
        pull_path, pull_mtime = newest_file_mtime("ops/watchdog/pulls", rf"^{src}-.*\.json$")
        # Also try to get fetched_at from the pull file content
        pull_fetched_at = None
        if pull_path:
            try:
                with open(REPO / pull_path) as f:
                    pull_data = json.load(f)
                pull_fetched_at = pull_data.get("fetched_at")
            except (json.JSONDecodeError, OSError):
                pass
        # Fallback: use health file's snapshot_path (data/raw/sources/<src>/...)
        # Many sources collect directly to data/raw/sources/ instead of ops/watchdog/pulls/
        snapshot_path = h.get("snapshot_path")
        snapshot_mtime = None
        if not pull_path and snapshot_path:
            sp = REPO / snapshot_path
            if sp.is_file():
                pull_path = snapshot_path
                snapshot_mtime = datetime.fromtimestamp(sp.stat().st_mtime, tz=timezone.utc).isoformat()
        c2_ts = pull_fetched_at or pull_mtime or snapshot_mtime
        c2_days = days_old(c2_ts)
        if c2_ts and c2_days is not None:
            if c2_days > 14:
                cps["c2_collection"] = {"timestamp": c2_ts, "status": "bad",
                    "reason": f"Last pull {c2_days:.0f}d ago ({pull_path}). Pull pipeline may be broken."}
            elif c2_days > 7:
                cps["c2_collection"] = {"timestamp": c2_ts, "status": "warn",
                    "reason": f"Last pull {c2_days:.0f}d ago. Awaiting publisher release."}
            else:
                cps["c2_collection"] = {"timestamp": c2_ts, "status": "ok",
                    "reason": f"Pulled {c2_ts} ({pull_path})."}
        else:
            # No pull file in ops/watchdog/pulls/ and no snapshot_path in health file
            cps["c2_collection"] = {"timestamp": None, "status": "unk",
                "reason": f"No pull file found for {src} in ops/watchdog/pulls/ and no snapshot_path in health file."}

        # C3: Supabase landing - from db_latest_arrived_at
        # cbsros is file-scraped (no Supabase table by design): the stage is
        # not applicable, which is an honest "ok", not a gap.
        if h.get("supabase_landing") is False and h.get("supabase_table") is None:
            cps["c3_supabase"] = {"timestamp": None, "status": "ok",
                "reason": "N/A by design: file-scraped source, no Supabase landing stage."}
        else:
            c3_ts = h.get("db_latest_arrived_at")
            c3_days = days_old(c3_ts)
            c3_rows = h.get("db_latest_rows")
            c3_table = h.get("supabase_table")
            if c3_ts and c3_days is not None:
                if c3_days > 14:
                    cps["c3_supabase"] = {"timestamp": c3_ts, "status": "bad",
                        "reason": f"Last Supabase landing {c3_days:.0f}d ago. Save pipeline may be broken."}
                elif c3_days > 7:
                    cps["c3_supabase"] = {"timestamp": c3_ts, "status": "warn",
                        "reason": f"Last Supabase landing {c3_days:.0f}d ago ({c3_rows} rows in {c3_table})."}
                else:
                    cps["c3_supabase"] = {"timestamp": c3_ts, "status": "ok",
                        "reason": f"{c3_rows} rows landed in {c3_table} {c3_days:.1f}d ago."}
            else:
                cps["c3_supabase"] = {"timestamp": None, "status": "unk",
                    "reason": "No Supabase landing timestamp in health file."}

        # C4: Snapshot/manifest - from snapshot_path file mtime
        snap_path = h.get("snapshot_path")
        c4_ts = None
        if snap_path:
            full_snap = REPO / snap_path
            if full_snap.exists():
                c4_ts = datetime.fromtimestamp(full_snap.stat().st_mtime, tz=timezone.utc).isoformat()
        c4_days = days_old(c4_ts)
        c4_vintage = h.get("content_vintage")
        if c4_ts and c4_days is not None:
            # Check if snapshot vintage matches DB latest (stuck detection)
            db_vintage = h.get("db_latest_vintage")
            stuck = db_vintage and c4_vintage and str(db_vintage) != str(c4_vintage)
            if stuck:
                cps["c4_snapshot"] = {"timestamp": c4_ts, "status": "warn",
                    "reason": f"Snapshot is {c4_vintage} but Supabase has {db_vintage}. Data is STUCK waiting for import."}
            elif c4_days > 14:
                cps["c4_snapshot"] = {"timestamp": c4_ts, "status": "bad",
                    "reason": f"Snapshot {c4_days:.0f}d old ({snap_path})."}
            else:
                cps["c4_snapshot"] = {"timestamp": c4_ts, "status": "ok",
                    "reason": f"Snapshot stamped {c4_days:.1f}d ago ({snap_path}, vintage {c4_vintage})."}
        else:
            cps["c4_snapshot"] = {"timestamp": None, "status": "unk",
                "reason": f"Snapshot path {snap_path} not found on disk."}

        # C5: Health verification - from checked_at + status
        c5_status = h.get("status", "unknown")
        c5_checked_at = h.get("_checked_at") or health_checked_at
        c5_days = days_old(c5_checked_at)
        c5_reason = h.get("failure_reason", "")
        if c5_status == "ok":
            cps["c5_health"] = {"timestamp": c5_checked_at,
                "status": "ok" if (c5_days or 99) < 2 else "warn",
                "reason": f"Health gate {c5_status} (checked {c5_days:.1f}d ago)." if c5_days else f"Health gate {c5_status}."}
        elif c5_status == "warning":
            cps["c5_health"] = {"timestamp": c5_checked_at, "status": "warn",
                "reason": f"Health gate warning: {c5_reason or 'awaiting publisher'}."}
        elif c5_status in ("failed", "missing", "error"):
            cps["c5_health"] = {"timestamp": c5_checked_at, "status": "bad",
                "reason": f"Health gate {c5_status}: {c5_reason or 'no reason given'}."}
        else:
            cps["c5_health"] = {"timestamp": c5_checked_at, "status": "unk",
                "reason": "No health record for this source."}

        # C6: Candidate build/review - from candidate dir + review file
        cand_dir = REPO / "output" / "comparison-candidates" / src
        cand_name, cand_mtime = newest_dir_mtime(f"output/comparison-candidates/{src}")
        _, review_mtime = newest_file_mtime("output/comparison-review", rf"^{src}-.*-review\.json$")
        # Use the newer of candidate build and review
        c6_ts = None
        for ts in [cand_mtime, review_mtime]:
            if ts and (not c6_ts or parse_iso(ts) > parse_iso(c6_ts)):
                c6_ts = ts
        c6_days = days_old(c6_ts)
        chain_result = chain_sources.get(src, "")
        if c6_ts and c6_days is not None:
            if c6_days > 14:
                cps["c6_candidate"] = {"timestamp": c6_ts, "status": "bad",
                    "reason": f"Last candidate/review {c6_days:.0f}d ago. Build pipeline may be broken."}
            elif c6_days > 7:
                cps["c6_candidate"] = {"timestamp": c6_ts, "status": "warn",
                    "reason": f"Last candidate/review {c6_days:.0f}d ago."}
            else:
                cps["c6_candidate"] = {"timestamp": c6_ts, "status": "ok",
                    "reason": f"Candidate built and reviewed {c6_days:.1f}d ago."}
        elif chain_result:
            # Fall back to chain status timestamp
            c6_days = days_old(chain_run_at)
            cps["c6_candidate"] = {"timestamp": chain_run_at,
                "status": "warn" if (c6_days or 99) > 2 else "ok",
                "reason": f"No candidate/review artifacts on disk. Chain reported '{chain_result}' at {chain_run_at}."}
        else:
            cps["c6_candidate"] = {"timestamp": None, "status": "unk",
                "reason": "No candidate or review artifacts found."}

        # C7: Fixture promotion - from promotion file (real promoted_at + review_verdict)
        promo_path, promo_mtime = newest_file_mtime("output/comparison-promotions", rf"^{src}-.*-promotion\.json$")
        promo_verdict = None
        promo_at = None
        if promo_path:
            try:
                with open(REPO / promo_path) as f:
                    promo_data = json.load(f)
                promo_verdict = promo_data.get("review_verdict")
                promo_at = promo_data.get("promoted_at")
            except (json.JSONDecodeError, OSError):
                pass
        c7_ts = promo_at or promo_mtime
        c7_days = days_old(c7_ts)
        if c7_ts and c7_days is not None:
            verdict_note = f" (verdict: {promo_verdict})" if promo_verdict else ""
            if promo_verdict and promo_verdict != "ready":
                cps["c7_promotion"] = {"timestamp": c7_ts, "status": "bad",
                    "reason": f"Last promotion had verdict '{promo_verdict}', not 'ready'. Promotion was blocked."}
            elif c7_days > 14:
                cps["c7_promotion"] = {"timestamp": c7_ts, "status": "bad",
                    "reason": f"Last promotion {c7_days:.0f}d ago{verdict_note}."}
            elif c7_days > 7:
                cps["c7_promotion"] = {"timestamp": c7_ts, "status": "warn",
                    "reason": f"Last promotion {c7_days:.0f}d ago{verdict_note}."}
            else:
                cps["c7_promotion"] = {"timestamp": c7_ts, "status": "ok",
                    "reason": f"Promoted {c7_days:.1f}d ago{verdict_note}."}
        else:
            # No formal promotion artifact. Direct fixture updates are the
            # intended workflow (per Jeremy 2026-09-30) — no review record required.
            cps["c7_promotion"] = {"timestamp": None, "status": "ok",
                "reason": "Direct fixture updates are the intended workflow; no formal promotion artifact required."}

        # C8: Sync/validation - fixture built_at vs dist content
        # CRITICAL: Check the actual data freshness (built_at inside the JSON),
        # not just file mtimes. The dashboard loads dist/assets/comparison-sources-data.json.
        fixture_days = days_old(fixture_built_at)
        dist_days = days_old(dist_mtime)
        # The dashboard loads from dist/assets/, not dist/modules/
        dist_fixture_path = REPO / "dist" / "assets" / "comparison-sources-data.json"
        dist_built_at = None
        if dist_fixture_path.exists():
            try:
                with open(dist_fixture_path) as f:
                    dist_data = json.load(f)
                dist_built_at = dist_data.get("built_at")
            except (json.JSONDecodeError, OSError):
                pass
        dist_content_days = days_old(dist_built_at)
        if fixture_built_at and dist_built_at:
            # First: is the SOURCE data fresh? (built_at inside the fixture)
            if fixture_days is not None and fixture_days > 7:
                cps["c8_sync"] = {"timestamp": fixture_built_at, "status": "bad",
                    "reason": f"Comparison data is {fixture_days:.0f}d old (built {fixture_built_at[:10]}). Rebuild chain has not produced fresh data."}
            elif fixture_days is not None and fixture_days > 3:
                cps["c8_sync"] = {"timestamp": fixture_built_at, "status": "warn",
                    "reason": f"Comparison data is {fixture_days:.0f}d old (built {fixture_built_at[:10]}). May be stale."}
            # Second: is the DEPLOYED data fresh? (built_at inside dist/assets/)
            elif dist_content_days is not None and dist_content_days > 7:
                cps["c8_sync"] = {"timestamp": dist_built_at, "status": "bad",
                    "reason": f"Deployed comparison data is {dist_content_days:.0f}d old (built {dist_built_at[:10]}). dist/ needs sync."}
            elif dist_content_days is not None and dist_content_days > 3:
                cps["c8_sync"] = {"timestamp": dist_built_at, "status": "warn",
                    "reason": f"Deployed comparison data is {dist_content_days:.0f}d old (built {dist_built_at[:10]})."}
            else:
                cps["c8_sync"] = {"timestamp": dist_built_at, "status": "ok",
                    "reason": f"Comparison data fresh (built {dist_built_at[:10]}, {(dist_content_days or 0):.1f}d ago)."}
        else:
            cps["c8_sync"] = {"timestamp": dist_built_at or dist_mtime, "status": "unk",
                "reason": "Cannot determine data freshness (missing built_at in fixture or dist)."}

        # C9: Deployment - use cached GitHub Pages deploy status (fetched once before loop)
        # Detects when Pages is serving stale content despite successful deploys
        # (CDN caching issues) or when deploys are failing.
        cps["c9_deploy"] = dict(pages_deploy)

        # C10: Rendered production output - fetch the LIVE served JSON and validate
        # what the production dashboard actually displays. Catches:
        # - week_designated labels wrong (e.g. "Week 2" when expecting "Week 4")
        # - value_weeks.monday stale
        # - served bytes differ from what the deploy pipeline publishes (CDN drift or failed sync)
        # - source combos missing (dashboard guard failures)
        cps["c10_rendered"] = {"timestamp": None, "status": "unk",
            "reason": "Rendered-output check not yet run."}
        try:
            import hashlib
            # Expected NFL content week from the pipeline's canonical week
            # function (see expected_content_week above) -- never a naive
            # days-since-kickoff count, which false-reds C10 near week
            # boundaries (2026-09-30: naive said Week 5, canonical is Week 4).
            expected_week = expected_content_week()
            expected_designation = f"Week {expected_week}"

            # Fetch live production JSON (WITHOUT cache-buster - we want to see what real users see,
            # including CDN-cached versions. If the CDN is serving stale "Week 2" labels, the monitor must catch it.)
            live_url = "https://jb-barrel-droid.github.io/fantasy-tools/assets/comparison-sources-data.json"
            req = urllib.request.Request(live_url, headers={"User-Agent": "fantasy-tools-monitor"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                live_bytes = resp.read()
            live_data = json.loads(live_bytes.decode())
            live_sha = hashlib.sha256(live_bytes).hexdigest()[:12]

            # Compare against the fixture bytes, not the committed dist/ copy.
            # The Pages workflow runs `make sync` before deploying, and sync
            # copies data/fixtures/current/comparison-sources-data.json
            # byte-identically into dist/assets/ — so the fixture is the true
            # "what should be live". The committed dist/ file can lag the
            # fixture by a commit (a fixture change that skipped the local sync
            # step); comparing live against that stale copy produced false
            # "Production output WRONG" alarms on 2026-09-30 (live correctly
            # served the fresh fixture while committed dist lagged one commit).
            fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
            fixture_sha = None
            if fixture_path.exists():
                fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()[:12]

            issues = []
            # Check 1: week_designated matches expected
            src_data = live_data.get("sources", {}).get(src, {})
            week_des = src_data.get("week_designated", "")
            if week_des != expected_designation:
                # Allow "rest of season" for ESPN, cbsros, and Razzball (rest-of-season
                # projections, not week-designated trade charts)
                if not (src in ("espn", "cbsros", "razzball") and week_des == "rest of season"):
                    issues.append(f"week_designated='{week_des}' (expected '{expected_designation}')")

            # Check 2: value_weeks.monday matches expected
            vw_monday = live_data.get("value_weeks", {}).get("monday")
            if vw_monday != expected_week:
                issues.append(f"value_weeks.monday={vw_monday} (expected {expected_week})")

            # Check 3: served bytes match what the deploy pipeline publishes (no CDN drift)
            if fixture_sha and live_sha != fixture_sha:
                issues.append(f"served bytes differ from fixture/ (live {live_sha} vs fixture {fixture_sha})")

            # Check 4: source has combos (dashboard needs them to render)
            combos = src_data.get("combos", {})
            if not combos:
                issues.append("source has no combos in served data (dashboard cannot render)")

            live_built = live_data.get("built_at", "")[:16]
            if issues:
                cps["c10_rendered"] = {"timestamp": iso_now(), "status": "bad",
                    "reason": f"Production output WRONG: {'; '.join(issues)}. Live built {live_built}."}
            else:
                # Also check the dashboard JS for stale hardcoded week labels
                # (e.g. "USA Today (Week 2)" hardcoded when expecting Week 4)
                try:
                    js_url = "https://jb-barrel-droid.github.io/fantasy-tools/assets/comparison-dashboard.js"
                    js_req = urllib.request.Request(js_url, headers={"User-Agent": "fantasy-tools-monitor"})
                    with urllib.request.urlopen(js_req, timeout=15) as js_resp:
                        js_text = js_resp.read().decode()
                    # Look for hardcoded "(Week N)" labels that don't match expected
                    stale_labels = []
                    for m in re.finditer(r'\((Week \d+)\)', js_text):
                        if m.group(1) != expected_designation:
                            # Find the label context (previous 30 chars)
                            start = max(0, m.start() - 40)
                            context = js_text[start:m.start()].split('\n')[-1][-30:]
                            stale_labels.append(f"{context.strip()}({m.group(1)})")
                    if stale_labels:
                        cps["c10_rendered"] = {"timestamp": iso_now(), "status": "bad",
                            "reason": f"Production JS has stale hardcoded labels: {'; '.join(stale_labels[:3])} (expected '{expected_designation}')."}
                    else:
                        cps["c10_rendered"] = {"timestamp": iso_now(), "status": "ok",
                            "reason": f"Production serves '{expected_designation}' labels, bytes match fixture/ ({live_sha}), {len(combos)} combos. Live built {live_built}."}
                except Exception as js_e:
                    # JS check failed, but JSON was ok - report ok with note
                    cps["c10_rendered"] = {"timestamp": iso_now(), "status": "ok",
                        "reason": f"Production serves '{expected_designation}' labels, bytes match fixture/ ({live_sha}), {len(combos)} combos. Live built {live_built}. (JS label check skipped: {str(js_e)[:40]})"}
        except Exception as e:
            cps["c10_rendered"] = {"timestamp": None, "status": "unk",
                "reason": f"Could not fetch live production JSON: {str(e)[:80]}."}

        result["sources"][src] = {
            "label": SRC_LABEL[src],
            "checkpoints": cps,
        }

    # Chain runner info (for the automation section)
    # Fix the mislabeled runner: "muse-cron" was a local direct run
    runner_label = chain_runner
    if chain_runner == "muse-cron":
        runner_label = "local-direct (mislabeled as muse-cron in status file)"
    result["chain"] = {
        "run_at": chain_run_at,
        "runner": chain_runner,
        "runner_label": runner_label,
        "success": chain_success,
        "run_age_days": days_old(chain_run_at),
        # A crashed/stale chain must not show green: if run_at is >36h old, force warn
        "stale": (days_old(chain_run_at) or 999) > 1.5,
    }

    # Adj curve pipeline: track all stages from input data -> live dashboard
    # Jeremy 2026-09-29: "The adj curves should update immediately as the new
    # weekly data populates. There is no reason it should be ad hoc and delayed,
    # it's part of the chain, and a section of the monitoring dashboard should
    # ensure all stages of the adj curves are moving forward from when the input
    # data updates all the way through to the live dash"
    result["adj_curve_pipeline"] = build_adj_curve_pipeline()

    # Methodology consistency: all as-published sources must use the same
    # reindex method and anchor at each transformation step (Jeremy 2026-10-01)
    result["methodology_consistency"] = build_methodology_consistency()

    # Scale agreement: native vs reindexed vs anchor per source x position.
    # Built by pipelines/build_scale_agreement.py; surfaced here so the fleet
    # headline counts it (a bad here must be impossible to hide).
    result["scale_agreement"] = build_scale_agreement_summary()

    # VORP translation freshness (JEG-70): the as-published sources' chart
    # values come from Supabase-translated grains wired through by
    # translate_via_vorp.py. A stale grain or a fallback-as-steady-state
    # silently reverts the chart to quantile-mapped values.
    result["vorp_translation"] = build_vorp_translation_summary()

    return result


def _reindex_pipeline_method():
    """Method string the reindex pipeline currently stamps into fixture fit
    metadata for as-published sources. Parsed from
    pipelines/reindex_comparison_section.py (the single source of truth) so
    the methodology-consistency check follows intentional methodology
    changes instead of flagging them. Fail-closed: raises if the pipeline
    no longer carries an identifiable flex_aware_pie method."""
    # Resolved from this file's own location, NOT the module-level REPO
    # (which tests may point at a fixture-only sandbox).
    pipelines_dir = Path(__file__).resolve().parent
    src = (pipelines_dir / "reindex_comparison_section.py").read_text()
    m = re.search(
        r'\["fit"\]\["flex_aware_pie"\]\s*=\s*\{[^}]*"method":\s*"([a-z0-9_]+)"',
        src,
        re.S,
    )
    if not m:
        raise RuntimeError(
            "build_pipeline_checkpoints: could not determine as-published "
            "reindex method from reindex_comparison_section.py"
        )
    return m.group(1)


def _reindex_pipeline_fit_key():
    """Fit-dict key the reindex pipeline writes for as-published sources.

    Parsed from pipelines/reindex_comparison_section.py (the single source of
    truth) alongside _reindex_pipeline_method(). The methodology-consistency
    check scopes its reindex method/anchor expectation to this key only --
    other fit keys (e.g. "vorp_translation", written by
    pipelines/translate_via_vorp.py with its own method family) are separate
    transformation steps with their own dedicated checks and must not be
    held to the reindex method. Fail-closed: raises unless the pipeline
    writes exactly one distinct fit key.
    """
    pipelines_dir = Path(__file__).resolve().parent
    src = (pipelines_dir / "reindex_comparison_section.py").read_text()
    keys = set(re.findall(r'\["fit"\]\["([a-z0-9_]+)"\]\s*=', src))
    if len(keys) != 1:
        raise RuntimeError(
            "build_pipeline_checkpoints: expected exactly one fit key written "
            f"by reindex_comparison_section.py, found {sorted(keys)}"
        )
    return keys.pop()


def build_scale_agreement_summary():
    """Surface the scale-agreement section status for the fleet headline.

    The full per-source x position analysis lives in
    dist/modules/scale-agreement.json (built by
    pipelines/build_scale_agreement.py). This function reads its top-level
    status so the monitor's fleet counter tallies it -- following the
    methodology_consistency pattern, a bad here must be impossible to hide.

    If scale-agreement.json is absent (builder not yet run), status is "unk",
    never a failure claim.
    """
    label = "Adj: legacy scale agreement (native vs reindexed vs anchor)"
    path = REPO / "dist" / "modules" / "scale-agreement.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "label": label,
            "status": "unk",
            "reason": "scale-agreement.json not available; run pipelines/build_scale_agreement.py",
            "timestamp": None,
        }
    vc = data.get("verdict_counts", {})
    return {
        "label": label,
        "status": data.get("status", "unk"),
        "reason": data.get("status_reason", ""),
        "timestamp": data.get("generated_at"),
        "verdict_counts": vc,
    }


def build_vorp_translation_summary():
    """VORP translation freshness for as-published sources (JEG-70).

    Reads the translation provenance blocks stamped by
    pipelines/translate_via_vorp.py into the fixture's as-published source
    combos. This is the end-to-end wired-through signal: what the chart
    actually serves, not what the pipeline claims.

    Expected: every combo that is not a qb-divergent sibling (data-driven
    guard in translate_via_vorp._qb_divergent_siblings, which pins those to
    reindex-fallback by design) has translation.method == "vorp-supabase"
    with grain.week == the current NFL week.

    Status:
      ok   - all expected grains at the current week via vorp-supabase
      warn - any expected grain week < current week (weekly refresh or chain
             wiring pending), or grain week not recorded (pre-JEG-70
             provenance; clears on the next chain run)
      bad  - any expected combo on reindex-fallback (fallback is the steady
             state -- JEG-70 acceptance criterion 3), or no provenance blocks
             at all (wiring never ran)
      unk  - fixture unreadable; never a failure claim
    """
    from translate_via_vorp import AS_PUBLISHED_SOURCES, _qb_divergent_siblings

    label = "VORP: legacy translation freshness (not Option C readiness)"
    fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    try:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {
            "label": label,
            "status": "unk",
            "reason": f"comparison-sources-data.json unreadable: {e}",
            "timestamp": None,
        }

    week = expected_content_week()
    sources = fixture.get("sources", {}) or {}
    stale: list[str] = []
    fallback: list[str] = []
    unrecorded: list[str] = []
    n_ok = 0
    n_expected = 0
    for source in AS_PUBLISHED_SOURCES:
        sdata = sources.get(source, {}) or {}
        combos = sdata.get("combos", {}) or {}
        guarded = _qb_divergent_siblings(source, sdata)
        for combo_name, combo in combos.items():
            if not isinstance(combo, dict):
                continue
            if combo_name in guarded:
                continue  # pinned to reindex-fallback by design (JEG-70)
            n_expected += 1
            t = combo.get("translation") or {}
            method = t.get("method")
            grain_week = (t.get("grain") or {}).get("week")
            tag = f"{source}/{combo_name}"
            if not t or not method:
                fallback.append(f"{tag}: no translation provenance (wiring never ran)")
            elif method == "reindex-fallback":
                fallback.append(f"{tag}: reindex-fallback is the steady state")
            elif grain_week is None:
                unrecorded.append(tag)
            elif grain_week < week:
                stale.append(f"{tag}: grain week {grain_week} < {week}")
            else:
                n_ok += 1

    timestamp = fixture.get("built_at")
    if fallback:
        return {
            "label": label,
            "status": "bad",
            "reason": f"{len(fallback)} combo(s) on reindex-fallback: " + "; ".join(fallback[:5]),
            "timestamp": timestamp,
            "n_ok": n_ok,
            "n_expected": n_expected,
        }
    problems = stale + [f"{t}: grain week not recorded" for t in unrecorded]
    if problems:
        return {
            "label": label,
            "status": "warn",
            "reason": f"{len(problems)} combo(s) stale or unrecorded: " + "; ".join(problems[:5]),
            "timestamp": timestamp,
            "n_ok": n_ok,
            "n_expected": n_expected,
        }
    return {
        "label": label,
        "status": "ok",
        "reason": f"All {n_expected} expected grains at week {week} via vorp-supabase.",
        "timestamp": timestamp,
        "n_ok": n_ok,
        "n_expected": n_expected,
    }


def build_methodology_consistency():
    """Check methodological consistency across sources at each transformation step.

    Jeremy 2026-10-01: "there needs to be consistency at each step of
    transformations." This catches the class of bug where one source (e.g.
    USA Today) silently keeps an old reindex method while others migrate.

    Checks:
      M1 Reindex method: all as-published sources (fantasycalc, fantasypros,
         usatoday, cbs) use the SAME method the reindex pipeline currently
         writes (single source of truth: reindex_comparison_section.py's
         flex_aware_pie fit). A source silently keeping an older method
         while others migrate is methodology drift and fails.
      M2 Combo coverage: each as-published source has all 3 scorings
         (full_12, half_12, standard_12).
      M3 Anchor consistency: all reindex fits anchor to espn_leg.

    Scope: M1/M3 apply ONLY to the reindex fit key (whatever key the reindex
    pipeline writes -- derived, not hardcoded). Other fit keys are separate
    transformation steps with their own dedicated checks: the
    "vorp_translation" step (method vorp-supabase, written by
    pipelines/translate_via_vorp.py) is covered by build_vorp_translation_summary,
    and legacy position-scoped fits (e.g. isotonic_pava on non-12-team combos)
    predate the current reindex contract. Holding them to the reindex method
    is a false bad (2026-10-03: the check flagged the intentional
    vorp-supabase translation step on all 12 combos).

    Status: ok/warn/bad. Any deviation is bad (methodology drift is a
    data-integrity failure, not a tolerance issue).
    """
    fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    fixture = {}
    if fixture_path.exists():
        try:
            with open(fixture_path) as f:
                fixture = json.load(f)
        except Exception:
            pass

    ASPUBLISHED = ["fantasycalc", "fantasypros", "usatoday", "cbs"]
    # EXPECTED_METHOD is derived from the reindex pipeline itself (single
    # source of truth), not hardcoded here. When Jeremy's methodology
    # directive changes the reindex math, the pipeline writes the new method
    # into fixture fit metadata and this check follows it. A source whose
    # fixture still carries an older method string is genuine drift and fails.
    # (2026-10-01: the flex-aware total-pie directive moved the method from
    # proportional_scaling_vorp_overlap to
    # proportional_scaling_flex_aware_per_position; the old hardcoded
    # constant falsely flagged the intentional change as a bad checkpoint.)
    EXPECTED_METHOD = _reindex_pipeline_method()
    EXPECTED_FIT_KEY = _reindex_pipeline_fit_key()
    EXPECTED_ANCHOR = "espn_leg"
    COMBOS = ["full_12", "half_12", "standard_12"]

    issues = []
    checked = 0

    for src in ASPUBLISHED:
        combos = fixture.get("sources", {}).get(src, {}).get("combos", {})
        for cn in COMBOS:
            # fantasycalc uses qb1/qb2 variants
            actual_cn = cn
            if cn not in combos:
                cands = [k for k in combos if k.startswith(cn)]
                actual_cn = cands[0] if cands else None
            if not actual_cn:
                issues.append(f"{src}/{cn}: combo missing from fixture")
                continue
            checked += 1
            fit = combos[actual_cn].get("fit", {})
            # Scope: only the reindex fit key is held to the reindex method
            # and anchor. Other fit keys (vorp_translation, legacy
            # position-scoped fits) are separate transformation steps with
            # their own checks; demanding the reindex method of them is a
            # false bad.
            reindex_fit = fit.get(EXPECTED_FIT_KEY)
            if not isinstance(reindex_fit, dict):
                issues.append(
                    f"{src}/{actual_cn}: missing {EXPECTED_FIT_KEY} fit "
                    f"(reindex step not recorded)"
                )
                continue
            method = reindex_fit.get("method")
            anchor = reindex_fit.get("anchor")
            if method and method != EXPECTED_METHOD:
                issues.append(
                    f"{src}/{actual_cn}/{EXPECTED_FIT_KEY}: method={method} "
                    f"(expected {EXPECTED_METHOD})"
                )
            if anchor and anchor != EXPECTED_ANCHOR:
                issues.append(
                    f"{src}/{actual_cn}/{EXPECTED_FIT_KEY}: anchor={anchor} "
                    f"(expected {EXPECTED_ANCHOR})"
                )

    if not checked:
        status, reason = "bad", "No as-published combos found in fixture."
    elif issues:
        status = "bad"
        reason = f"{len(issues)} methodology inconsistencies: " + "; ".join(issues[:5])
        if len(issues) > 5:
            reason += f" (+{len(issues) - 5} more)"
    else:
        status, reason = "ok", (
            f"All {checked} as-published combos use {EXPECTED_METHOD} "
            f"anchored to {EXPECTED_ANCHOR} on the {EXPECTED_FIT_KEY} reindex fit "
            f"(translation step checked separately)."
        )

    return {
        "label": "VORP / Adj: legacy methodology consistency",
        "what": "Legacy reindex method/anchor consistency; not eight-group VORP or shared reweight readiness",
        "timestamp": iso_now(),
        "status": status,
        "reason": reason,
        "expected_method": EXPECTED_METHOD,
        "expected_fit_key": EXPECTED_FIT_KEY,
        "expected_anchor": EXPECTED_ANCHOR,
        "combos_checked": checked,
        "issues": issues,
    }


def build_adj_curve_pipeline():
    """Build the adj curve pipeline stage statuses.

    Tracks the linear flow for _adjusted curves:
      A1 Input data    - source snapshots fresh for current NFL week
      A2 Fit executed  - adjustment-inputs.json generated after input data
      A3 Sections baked - _adjusted sections have fit_bake_id matching inputs version
      A4 Synced to dist - dist/assets/adjustment-inputs.json matches app/ version
      A5 Live           - served adjustment-inputs.json matches local version

    Each stage: {label, what, timestamp, status, reason}
    Status: ok/warn/bad/unk. A stage is only ok if it ran AFTER the previous stage.
    """
    import hashlib
    import urllib.request

    stages = {}

    # A1: Input data - check source snapshot freshness
    # The 4 adjusted sources: fantasycalc, usatoday, fantasypros, cbs
    adj_sources = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
    fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
    fixture = {}
    fixture_built_at = None
    if fixture_path.exists():
        try:
            with open(fixture_path) as f:
                fixture = json.load(f)
            fixture_built_at = fixture.get("built_at")
        except:
            pass

    # Check each adj source has data in the fixture
    sources_with_data = []
    for src in adj_sources:
        if src in fixture.get("sources", {}):
            combos = fixture["sources"][src].get("combos", {})
            if combos:
                sources_with_data.append(src)

    if len(sources_with_data) == 4:
        stages["a1_input"] = {
            "label": "A1 · Input data",
            "what": "All 4 adj sources (FC, USAT, FP, CBS) have data in the fixture",
            "timestamp": fixture_built_at,
            "status": "ok",
            "reason": f"All 4 sources present in fixture (built {fixture_built_at}).",
        }
    elif sources_with_data:
        stages["a1_input"] = {
            "label": "A1 · Input data",
            "what": "All 4 adj sources (FC, USAT, FP, CBS) have data in the fixture",
            "timestamp": fixture_built_at,
            "status": "warn",
            "reason": f"Only {len(sources_with_data)}/4 sources have data: {', '.join(sources_with_data)}.",
        }
    else:
        stages["a1_input"] = {
            "label": "A1 · Input data",
            "what": "All 4 adj sources (FC, USAT, FP, CBS) have data in the fixture",
            "timestamp": fixture_built_at,
            "status": "bad",
            "reason": "No adj source data in fixture.",
        }

    # A2: Fit executed - check adjustment-inputs.json
    inputs_path = REPO / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"
    inputs = {}
    inputs_generated_at = None
    inputs_version = None
    if inputs_path.exists():
        try:
            with open(inputs_path) as f:
                inputs = json.load(f)
            inputs_generated_at = inputs.get("generated_at")
            inputs_version = inputs.get("version")
        except:
            pass

    # Fit should be recent (within 2 days) — the exact ordering vs fixture
    # built_at is not meaningful because the fixture is rebuilt AFTER the fit
    # to bake in the _adjusted sections (updating built_at).
    # What matters: fit exists, has a version, and is fresh.
    fit_age_days = days_old(inputs_generated_at) if inputs_generated_at else 999

    if inputs_generated_at and inputs_version and fit_age_days <= 2:
        stages["a2_fit"] = {
            "label": "A2 · Fit executed",
            "what": "build_adjustment_inputs.py ran recently (adjustment-inputs.json fresh)",
            "timestamp": inputs_generated_at,
            "status": "ok",
            "reason": f"Fit version {inputs_version} generated {inputs_generated_at} ({fit_age_days:.1f}d ago).",
        }
    elif inputs_generated_at and inputs_version:
        stages["a2_fit"] = {
            "label": "A2 · Fit executed",
            "what": "build_adjustment_inputs.py ran recently (adjustment-inputs.json fresh)",
            "timestamp": inputs_generated_at,
            "status": "warn",
            "reason": f"Fit version {inputs_version} generated {inputs_generated_at} ({fit_age_days:.1f}d ago) — stale, needs re-run.",
        }
    else:
        stages["a2_fit"] = {
            "label": "A2 · Fit executed",
            "what": "build_adjustment_inputs.py ran recently (adjustment-inputs.json fresh)",
            "timestamp": inputs_generated_at,
            "status": "bad",
            "reason": "adjustment-inputs.json missing or unreadable.",
        }

    # A3: Sections baked - check _adjusted sections have matching fit_bake_id
    adj_sections_ok = []
    adj_sections_bad = []
    for src in adj_sources:
        adj_key = f"{src}_adjusted"
        adj_section = fixture.get("sources", {}).get(adj_key, {})
        fit_bake_id = adj_section.get("fit_bake_id")
        if fit_bake_id and fit_bake_id == inputs_version:
            adj_sections_ok.append(src)
        else:
            adj_sections_bad.append(f"{src} (fit_bake_id={fit_bake_id})")

    if len(adj_sections_ok) == 4:
        stages["a3_sections"] = {
            "label": "A3 · Sections baked",
            "what": "_adjusted fixture sections built with current fit_bake_id",
            "timestamp": fixture_built_at,
            "status": "ok",
            "reason": f"All 4 _adjusted sections have fit_bake_id={inputs_version}.",
        }
    elif adj_sections_ok:
        stages["a3_sections"] = {
            "label": "A3 · Sections baked",
            "what": "_adjusted fixture sections built with current fit_bake_id",
            "timestamp": fixture_built_at,
            "status": "warn",
            "reason": f"Only {len(adj_sections_ok)}/4 match: {', '.join(adj_sections_ok)}. Mismatched: {', '.join(adj_sections_bad)}.",
        }
    else:
        stages["a3_sections"] = {
            "label": "A3 · Sections baked",
            "what": "_adjusted fixture sections built with current fit_bake_id",
            "timestamp": fixture_built_at,
            "status": "bad",
            "reason": f"No _adjusted sections match fit version {inputs_version}. Found: {', '.join(adj_sections_bad)}.",
        }

    # A4: Synced to dist - check dist/assets/adjustment-inputs.json matches app/
    dist_inputs_path = REPO / "dist" / "assets" / "adjustment-inputs.json"
    dist_version = None
    dist_mtime = None
    if dist_inputs_path.exists():
        try:
            with open(dist_inputs_path) as f:
                dist_data = json.load(f)
            dist_version = dist_data.get("version")
            dist_mtime = datetime.fromtimestamp(dist_inputs_path.stat().st_mtime, tz=timezone.utc).isoformat()
        except:
            pass

    if dist_version and dist_version == inputs_version:
        stages["a4_sync"] = {
            "label": "A4 · Synced to dist",
            "what": "dist/assets/adjustment-inputs.json matches app/ version (ready for deploy)",
            "timestamp": dist_mtime,
            "status": "ok",
            "reason": f"dist/ version {dist_version} matches app/ version.",
        }
    elif dist_version:
        stages["a4_sync"] = {
            "label": "A4 · Synced to dist",
            "what": "dist/assets/adjustment-inputs.json matches app/ version (ready for deploy)",
            "timestamp": dist_mtime,
            "status": "warn",
            "reason": f"dist/ version {dist_version} != app/ version {inputs_version} — needs sync.",
        }
    else:
        stages["a4_sync"] = {
            "label": "A4 · Synced to dist",
            "what": "dist/assets/adjustment-inputs.json matches app/ version (ready for deploy)",
            "timestamp": None,
            "status": "bad",
            "reason": "dist/assets/adjustment-inputs.json missing.",
        }

    # A5: Live - check served adjustment-inputs.json matches local AND has COMPLETE cells
    # Jeremy 2026-09-29: "Fix and ensure monitoring dash covers it" — A5 must verify
    # the ACTUAL pause condition. The widget's adjustedCurvePaused() requires:
    #   1. source status == "live" AND
    #   2. cells for ALL 8 position/tier combos (QB/RB/WR/TE x starter/bench)
    # Partial sources (7/8, 4/8) stay paused by design — "so raw published values
    # are never silently mixed into an adjusted projection."
    live_version = None
    live_generated_at = None
    live_cells_status = {}
    live_cells_complete = {}
    try:
        url = "https://jb-barrel-droid.github.io/fantasy-tools/assets/adjustment-inputs.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            live_data = json.load(resp)
        live_version = live_data.get("version")
        live_generated_at = live_data.get("generated_at")
        # Check the actual pause condition: each source needs 8/8 cells AND status live
        REQUIRED_CELLS = 8  # 4 positions x 2 tiers
        for src in ["fantasycalc", "usatoday", "fantasypros", "cbs"]:
            entry = live_data.get("sources", {}).get(src, {})
            cells = entry.get("cells", [])
            n_cells = len(cells) if isinstance(cells, list) else 0
            status = entry.get("status", "unknown")
            live_cells_status[src] = n_cells
            # Complete = 8/8 cells AND status live
            live_cells_complete[src] = (n_cells >= REQUIRED_CELLS and status == "live")
    except Exception as e:
        live_version = None

    # A curve is paused if its source doesn't have complete 8/8 live cells
    paused_sources = [src for src, complete in live_cells_complete.items() if not complete]
    all_complete = len(paused_sources) == 0 and len(live_cells_complete) == 4

    if live_version and live_version == inputs_version and all_complete:
        stages["a5_live"] = {
            "label": "A5 · Live",
            "what": "Production serves current adjustment-inputs.json with complete 8/8 live cells for all 4 sources (curves unpaused)",
            "timestamp": live_generated_at,
            "status": "ok",
            "reason": f"Live version {live_version} matches local. All 4 sources have 8/8 live cells.",
        }
    elif live_version and live_version == inputs_version and paused_sources:
        # Version matches but cells incomplete — curves WILL BE PAUSED by design
        details = ", ".join([f"{s}({live_cells_status.get(s, 0)}/8)" for s in paused_sources])
        stages["a5_live"] = {
            "label": "A5 · Live",
            "what": "Production serves current adjustment-inputs.json with complete 8/8 live cells for all 4 sources (curves unpaused)",
            "timestamp": live_generated_at,
            "status": "bad",
            "reason": f"Live version {live_version} matches, but incomplete cells — {details} — " +
                      "those curves ARE PAUSED on the dashboard (fail-closed by design). " +
                      "Fit needs to produce complete 8/8 cells.",
        }
    elif live_version:
        stages["a5_live"] = {
            "label": "A5 · Live",
            "what": "Production serves current adjustment-inputs.json with complete 8/8 live cells for all 4 sources (curves unpaused)",
            "timestamp": live_generated_at,
            "status": "bad",
            "reason": f"Live version {live_version} != local version {inputs_version} — deploy needed. Curves may be paused on stale inputs.",
        }
    else:
        stages["a5_live"] = {
            "label": "A5 · Live",
            "what": "Production serves current adjustment-inputs.json with complete 8/8 live cells for all 4 sources (curves unpaused)",
            "timestamp": None,
            "status": "unk",
            "reason": "Could not fetch live adjustment-inputs.json.",
        }

    return stages


def main():
    result = build_checkpoints()
    out_path = REPO / "output" / "pipeline-checkpoints.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {out_path}")

    # Also sync to dist for the deployed dashboard
    dist_path = REPO / "dist" / "modules" / "pipeline-checkpoints.json"
    dist_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dist_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {dist_path}")


if __name__ == "__main__":
    main()
