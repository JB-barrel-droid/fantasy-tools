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
SOURCES = ["espn", "cbs", "fantasycalc", "fantasypros", "usatoday"]
SRC_LABEL = {
    "espn": "ESPN",
    "cbs": "CBS",
    "fantasycalc": "FantasyCalc",
    "fantasypros": "FantasyPros",
    "usatoday": "USA Today",
}

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


def build_checkpoints():
    # Load health file
    health_path = REPO / "output" / "source-import-health.json"
    health = {}
    health_checked_at = None
    if health_path.exists():
        with open(health_path) as f:
            health = json.load(f)
        health_checked_at = health.get("checked_at")

    # Load fixture
    fixture_path = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
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

    for src in SOURCES:
        h = health.get("sources", {}).get(src, {})
        cps = {}

        # C1: Publication/discovery - from content_vintage (when publisher released)
        c1_ts = h.get("content_vintage")
        # content_vintage may be a date or "Week N"; try to parse
        c1_days = days_old(c1_ts)
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

        # C2: Raw collection - from pull file
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
        c2_ts = pull_fetched_at or pull_mtime
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
            # Some sources (espn, fantasycalc, fantasypros) may not use watchdog pulls
            cps["c2_collection"] = {"timestamp": None, "status": "unk",
                "reason": f"No pull file found for {src} in ops/watchdog/pulls/. May use a different collection path."}

        # C3: Supabase landing - from db_latest_arrived_at
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
        c5_days = days_old(health_checked_at)
        c5_reason = h.get("failure_reason", "")
        if c5_status == "ok":
            cps["c5_health"] = {"timestamp": health_checked_at,
                "status": "ok" if (c5_days or 99) < 2 else "warn",
                "reason": f"Health gate {c5_status} (checked {c5_days:.1f}d ago)." if c5_days else f"Health gate {c5_status}."}
        elif c5_status == "warning":
            cps["c5_health"] = {"timestamp": health_checked_at, "status": "warn",
                "reason": f"Health gate warning: {c5_reason or 'awaiting publisher'}."}
        elif c5_status in ("failed", "missing", "error"):
            cps["c5_health"] = {"timestamp": health_checked_at, "status": "bad",
                "reason": f"Health gate {c5_status}: {c5_reason or 'no reason given'}."}
        else:
            cps["c5_health"] = {"timestamp": health_checked_at, "status": "unk",
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
            cps["c7_promotion"] = {"timestamp": None, "status": "unk",
                "reason": "No promotion artifacts found."}

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

        # C9: Deployment - check GitHub Pages deploy status via API
        # Detects when Pages is serving stale content despite successful deploys
        # (CDN caching issues) or when deploys are failing.
        cps["c9_deploy"] = {"timestamp": None, "status": "unk",
            "reason": "Deploy status check not yet implemented in Python; browser checks Actions API live."}
        try:
            import urllib.request
            # Get last pages.yml workflow run from GitHub Actions API
            req = urllib.request.Request(
                "https://api.github.com/repos/JB-barrel-droid/fantasy-tools/actions/workflows/pages.yml/runs?per_page=1",
                headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "fantasy-tools-monitor"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            runs = data.get("workflow_runs", [])
            if runs:
                last_run = runs[0]
                run_status = last_run.get("status")
                run_conclusion = last_run.get("conclusion")
                run_updated = last_run.get("updated_at")
                run_days = days_old(run_updated)
                if run_status != "completed" or run_conclusion != "success":
                    cps["c9_deploy"] = {"timestamp": run_updated, "status": "bad",
                        "reason": f"Last Pages deploy: {run_status}/{run_conclusion}. Deploy may have failed."}
                elif run_days is not None and run_days > 2:
                    cps["c9_deploy"] = {"timestamp": run_updated, "status": "warn",
                        "reason": f"Last successful Pages deploy {run_days:.1f}d ago. Content may be stale."}
                else:
                    cps["c9_deploy"] = {"timestamp": run_updated, "status": "ok",
                        "reason": f"Pages deployed successfully {(run_days or 0):.1f}d ago."}
        except Exception as e:
            # API check failed; keep as unk with reason
            cps["c9_deploy"] = {"timestamp": None, "status": "unk",
                "reason": f"Could not check Pages API: {str(e)[:60]}. Browser checks live."}

        # C10: Rendered production output - fetch the LIVE served JSON and validate
        # what the production dashboard actually displays. Catches:
        # - week_designated labels wrong (e.g. "Week 2" when expecting "Week 4")
        # - value_weeks.monday stale
        # - served bytes differ from repo dist/ (CDN drift or failed sync)
        # - source combos missing (dashboard guard failures)
        cps["c10_rendered"] = {"timestamp": None, "status": "unk",
            "reason": "Rendered-output check not yet run."}
        try:
            import hashlib
            # Expected NFL week from date (2026 season: Week 1 Thursday = 2026-09-03)
            season_start = datetime(2026, 9, 3, tzinfo=timezone.utc)
            now_utc = datetime.now(timezone.utc)
            expected_week = ((now_utc - season_start).days // 7) + 1
            expected_designation = f"Week {expected_week}"

            # Fetch live production JSON (WITHOUT cache-buster - we want to see what real users see,
            # including CDN-cached versions. If the CDN is serving stale "Week 2" labels, the monitor must catch it.)
            live_url = "https://jb-barrel-droid.github.io/fantasy-tools/assets/comparison-sources-data.json"
            req = urllib.request.Request(live_url, headers={"User-Agent": "fantasy-tools-monitor"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                live_bytes = resp.read()
            live_data = json.loads(live_bytes.decode())
            live_sha = hashlib.sha256(live_bytes).hexdigest()[:12]

            # Compare against local dist bytes
            dist_path = REPO / "dist" / "assets" / "comparison-sources-data.json"
            dist_sha = None
            if dist_path.exists():
                dist_sha = hashlib.sha256(dist_path.read_bytes()).hexdigest()[:12]

            issues = []
            # Check 1: week_designated matches expected
            src_data = live_data.get("sources", {}).get(src, {})
            week_des = src_data.get("week_designated", "")
            if week_des != expected_designation:
                # Allow "rest of season" for ESPN (not week-designated)
                if not (src == "espn" and week_des == "rest of season"):
                    issues.append(f"week_designated='{week_des}' (expected '{expected_designation}')")

            # Check 2: value_weeks.monday matches expected
            vw_monday = live_data.get("value_weeks", {}).get("monday")
            if vw_monday != expected_week:
                issues.append(f"value_weeks.monday={vw_monday} (expected {expected_week})")

            # Check 3: served bytes match local dist (no CDN drift)
            if dist_sha and live_sha != dist_sha:
                issues.append(f"served bytes differ from dist/ (live {live_sha} vs dist {dist_sha})")

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
                    import re
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
                            "reason": f"Production serves '{expected_designation}' labels, bytes match dist/ ({live_sha}), {len(combos)} combos. Live built {live_built}."}
                except Exception as js_e:
                    # JS check failed, but JSON was ok - report ok with note
                    cps["c10_rendered"] = {"timestamp": iso_now(), "status": "ok",
                        "reason": f"Production serves '{expected_designation}' labels, bytes match dist/ ({live_sha}), {len(combos)} combos. Live built {live_built}. (JS label check skipped: {str(js_e)[:40]})"}
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

    return result


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
