#!/usr/bin/env python3
"""Alerts for real failures, delivered once per state change (GAP-ALERT-CHANNEL).

Runs in health-artifacts.yml after the monitor files are built. It reads the
files the monitor already publishes, decides which alert conditions hold now,
and reconciles that set with what is already open:

    rebuild-chain-failing   the comparison chain's latest run failed or did not
                            run, and nothing has published for over
                            REBUILD_STALE_HOURS (a failing chain holds the
                            fixture, so the site stops getting fresh numbers)
    source-stuck-<source>   no new data for a source has landed for more than
                            SOURCE_STUCK_DAYS (newest of: Supabase landing
                            time, content date)
    monitor-unreadable      the summary could not be read or the evaluator did
                            not run, so every other signal is unknown
    security-regression     public.monitoring_security_posture() reports a
                            table without RLS, an anon/authenticated write
                            grant, a public definer view, a mutable
                            search_path or an anon-executable definer function
    identity-unmatched-<source>  more than identity_queue.OPEN_NAMES_ALERT
                            player names from one source seen in the last
                            week still resolve to no player (JEG-438)

Everything else on the monitor (staleness, holds, yellow checks) stays a
warning on the page, per Jeremy's pre-launch direction. Nothing here can fail
or block a deploy: the script always exits 0 unless its own arguments are bad.

Delivery is channel-agnostic. The GitHub-issue channel is the default: one open
issue per alert key (label `ops-alert`, hidden key marker in the body), opened
when the condition starts and closed with a comment when it clears; while it
stays open the body is updated silently (no new notification). Issues opened
by the workflow mention the repository owner, so GitHub emails Jeremy with no
new account or secret. Set ALERT_WEBHOOK_URL (a Slack- or Discord-compatible
incoming webhook) to also post each open/close transition there.

If GitHub Issues are disabled for the repository (the API answers 410, or the
repo reports has_issues=false), the issue channel cannot deliver. That is never
silent: the step prints a warning annotation naming the cause, every alert that
holds is written to the job summary ($GITHUB_STEP_SUMMARY), and the webhook (if
set) gets every holding alert, since there is no issue to dedupe against.

    python3 pipelines/monitor_alerts.py --summary output/monitoring-summary.json \
        --import-health output/source-import-health.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

LABEL = "ops-alert"
SOURCE_STUCK_DAYS = 10      # weekly sources + 3 days of slack
REBUILD_STALE_HOURS = 12    # two missed 6-hourly chain runs
KEY_MARKER = re.compile(r"<!--\s*ops-alert-key:\s*([a-z0-9_.-]+)\s*-->")


@dataclass(frozen=True)
class Alert:
    key: str
    title: str
    body: str


def parse_ts(value):
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        try:
            dt = datetime.strptime(v[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "never"


# ---------------------------------------------------------------- conditions

def rebuild_chain_alert(summary, now, stale_hours=REBUILD_STALE_HOURS):
    check = next((c for c in summary.get("checks") or [] if c.get("check_id") == "rebuild_chain"), None)
    if not check or check.get("state") not in ("error", "missed"):
        return None
    last_ok = parse_ts(check.get("last_ok_at"))
    if last_ok and now - last_ok <= timedelta(hours=stale_hours):
        return None  # one red run between green ones: the page shows it; no alert
    return Alert(
        "rebuild-chain-failing",
        "Rebuild chain is failing: the site is not getting fresh numbers",
        f"`rebuild-chain.yml` state: **{check.get('state')}** ({check.get('reason')}).\n"
        f"Last successful run: {_fmt(last_ok)} (alert threshold {stale_hours} h).\n\n"
        "A failing chain keeps the last published fixture, so values on the site stop updating. "
        "Open the latest rebuild-chain run's annotations for the failing step.")


def source_stuck_alerts(import_health, now, stuck_days=SOURCE_STUCK_DAYS):
    out = []
    for source, entry in sorted((import_health.get("sources") or {}).items()):
        entry = entry or {}
        times = [parse_ts(entry.get("db_latest_arrived_at")), parse_ts(entry.get("vintage_date"))]
        cv = entry.get("content_vintage")
        if isinstance(cv, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", cv):
            times.append(parse_ts(cv))
        newest = max((t for t in times if t), default=None)
        if newest is not None and now - newest <= timedelta(days=stuck_days):
            continue
        age = "unknown age" if newest is None else f"{(now - newest).days} days"
        out.append(Alert(
            f"source-stuck-{source}",
            f"{source}: no new data for {age}",
            f"No new `{source}` data has landed for **{age}** (alert threshold {stuck_days} days).\n"
            f"Newest landing or content date: {_fmt(newest)}; content vintage `{entry.get('content_vintage')}`; "
            f"import status `{entry.get('status')}`.\n\n"
            f"Reason recorded by the import-health check: {entry.get('failure_reason') or 'none'}"))
    return out


def monitor_unreadable_alert(summary):
    reason = summary.get("read_error") or ("evaluator did not run" if summary.get("evaluator_stale") else None)
    if not reason:
        return None
    return Alert("monitor-unreadable", "Monitor could not be read: every status is unknown",
                 f"`public.monitoring_refresh_summary()` failed or the evaluator did not run: {reason}.")


def security_alert(summary):
    sec = summary.get("security")
    if not isinstance(sec, dict) or sec.get("read_error") or sec.get("ok") is not False:
        return None
    counts = {k: sec.get(k) for k in ("tables_without_rls", "anon_or_auth_write_grants", "public_definer_views",
                                      "mutable_search_path_functions", "anon_executable_definer_functions")}
    lines = "\n".join(f"- {k}: {v}" for k, v in counts.items() if v)
    return Alert("security-regression", "Supabase security regression: a public table or grant is open",
                 f"`public.monitoring_security_posture()` is not clean:\n{lines}\n\n"
                 f"Details: `{json.dumps(sec.get('details') or {}, sort_keys=True)[:1500]}`\n\n"
                 "Fix pattern: supabase/migrations/20261008_security_lockdown.sql.")


def identity_unmatched_alerts(summary):
    """JEG-438: a source with more open player names (unmatched / review /
    provisional, seen in the window) than the summary's threshold. A failed
    identity read raises nothing here: the summary carries the read_error."""
    ident = summary.get("identity")
    if not isinstance(ident, dict) or ident.get("read_error"):
        return []
    threshold = ident.get("alert_threshold")
    if not isinstance(threshold, int):
        return []
    out = []
    for source, c in sorted((ident.get("open_by_source") or {}).items()):
        n = (c or {}).get("open") or 0
        if n <= threshold:
            continue
        names = ", ".join((c.get("names") or [])[:30])
        out.append(Alert(
            f"identity-unmatched-{re.sub(r'[^a-z0-9_.-]', '-', str(source).lower()) or 'unknown'}",
            f"{source}: {n} player names do not resolve to a player",
            f"`{source}` has **{n}** open player names (unmatched {c.get('unmatched')}, review "
            f"{c.get('review')}, provisional {c.get('provisional')}) seen in the last "
            f"{ident.get('window_days')} days; alert threshold {threshold}.\n\n"
            f"Names: {names}\n\n"
            "Their rows are left out of that source's saved values (never guessed). Check each in "
            "`public.player_name_aliases` and `pipelines/reconcile_player_identity.py`'s report; add a "
            "verified spelling to `data/inputs/player_aliases.json` when it is the same player."))
    return out


def evaluate(summary, import_health, now, stuck_days=SOURCE_STUCK_DAYS, stale_hours=REBUILD_STALE_HOURS):
    """All alert conditions that hold now (list of Alert, unique keys)."""
    summary = summary or {}
    alerts = [monitor_unreadable_alert(summary), security_alert(summary)]
    if not summary.get("read_error"):
        alerts.append(rebuild_chain_alert(summary, now, stale_hours))
    alerts.extend(identity_unmatched_alerts(summary))
    alerts.extend(source_stuck_alerts(import_health or {}, now, stuck_days))
    return [a for a in alerts if a]


# ------------------------------------------------------------- reconciliation

def issue_key(issue):
    m = KEY_MARKER.search(issue.get("body") or "")
    return m.group(1) if m else None


def render_body(alert, now, mention):
    return (f"<!-- ops-alert-key: {alert.key} -->\n{alert.body}\n\n---\n"
            f"Checked {_fmt(now)} by health-artifacts.yml. This issue closes itself when the condition clears."
            + (f"\n\ncc @{mention}" if mention else ""))


def plan(alerts, open_issues):
    """Return (to_open, to_update, to_close). Pure; one open issue per key."""
    by_key = {}
    for issue in open_issues:
        k = issue_key(issue)
        if k and k not in by_key:
            by_key[k] = issue
    active = {a.key: a for a in alerts}
    to_open = [a for k, a in active.items() if k not in by_key]
    to_update = [(by_key[k], a) for k, a in active.items() if k in by_key]
    to_close = [i for k, i in by_key.items() if k not in active]
    return to_open, to_update, to_close


class IssuesDisabled(RuntimeError):
    """The repository has GitHub Issues turned off (HTTP 410 / has_issues=false)."""


class GitHubIssues:
    """Minimal REST client (GITHUB_TOKEN with issues: write)."""

    def __init__(self, repo, token, api="https://api.github.com"):
        self.base, self.token = f"{api}/repos/{repo}", token

    def _call(self, method, path, body=None):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 410:  # "Issues has been disabled in this repository."
                raise IssuesDisabled(f"{method} {path or '/'}: HTTP 410") from e
            raise
        return json.loads(raw) if raw else None

    def ensure_label(self):
        # With Issues off, GET /issues still answers 200 [] and only the create
        # fails (410), so check the repo flag first: no partial reconcile.
        if (self._call("GET", "") or {}).get("has_issues") is False:
            raise IssuesDisabled("repository has_issues=false")
        try:
            self._call("POST", "/labels", {"name": LABEL, "color": "d73a4a",
                                           "description": "Automated monitoring alert (health-artifacts.yml)"})
        except urllib.error.HTTPError as e:
            if e.code != 422:  # 422 = already exists
                raise

    def open_issues(self):
        return [i for i in self._call("GET", f"/issues?state=open&labels={LABEL}&per_page=100") or []
                if "pull_request" not in i]

    def create(self, title, body):
        return self._call("POST", "/issues", {"title": f"[{LABEL}] {title}", "body": body, "labels": [LABEL]})

    def update(self, number, body):
        return self._call("PATCH", f"/issues/{number}", {"body": body})

    def close(self, number, comment):
        self._call("POST", f"/issues/{number}/comments", {"body": comment})
        return self._call("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})


def post_webhook(url, text):
    req = urllib.request.Request(url, method="POST", data=json.dumps({"text": text, "content": text}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15):
        pass


def reconcile(alerts, client, now, mention=None, webhook=None, log=print):
    client.ensure_label()
    to_open, to_update, to_close = plan(alerts, client.open_issues())
    for a in to_open:
        issue = client.create(a.title, render_body(a, now, mention))
        log(f"opened #{(issue or {}).get('number')}: {a.key}")
        if webhook:
            post_webhook(webhook, f"ALERT {a.title} ({(issue or {}).get('html_url', '')})")
    for issue, a in to_update:
        client.update(issue["number"], render_body(a, now, None))
        log(f"still open #{issue['number']}: {a.key}")
    for issue in to_close:
        client.close(issue["number"], f"Cleared at {_fmt(now)}: the condition no longer holds.")
        log(f"closed #{issue['number']}: {issue_key(issue)}")
        if webhook:
            post_webhook(webhook, f"CLEARED {issue.get('title')}")
    return to_open, to_update, to_close


def write_step_summary(alerts, note=None, path=None):
    """Append the alerts that hold to the job summary, so a run whose delivery
    channel is down still shows them. No-op outside Actions."""
    path = path or os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return False
    lines = ["## Ops alerts", ""]
    if note:
        lines += [f"> **{note}**", ""]
    if alerts:
        for a in alerts:
            lines += [f"### {a.title}", f"`{a.key}`", "", a.body, ""]
    else:
        lines.append("No alert condition holds.")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return True


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - a missing file is itself a signal
        return {"read_error": f"{path}: {type(exc).__name__}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--import-health", required=True)
    ap.add_argument("--stuck-days", type=float, default=float(os.environ.get("ALERT_SOURCE_STUCK_DAYS", SOURCE_STUCK_DAYS)))
    ap.add_argument("--stale-hours", type=float, default=float(os.environ.get("ALERT_REBUILD_STALE_HOURS", REBUILD_STALE_HOURS)))
    ap.add_argument("--dry-run", action="store_true", help="print the plan; touch no issue")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    health = _load(args.import_health)
    alerts = evaluate(_load(args.summary), {} if health.get("read_error") else health, now,
                      args.stuck_days, args.stale_hours)
    for a in alerts:
        print(f"::warning title=ops-alert {a.key}::{a.title}")
    print(f"{len(alerts)} alert condition(s) hold: {', '.join(a.key for a in alerts) or 'none'}")
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if args.dry_run or not (repo and token):
        print("dry run: no issues touched" if args.dry_run else "GITHUB_REPOSITORY/GITHUB_TOKEN not set: no issues touched")
        return 0
    webhook = os.environ.get("ALERT_WEBHOOK_URL") or None
    note = None
    try:
        reconcile(alerts, GitHubIssues(repo, token), now,
                  mention=os.environ.get("ALERT_MENTION") or os.environ.get("GITHUB_REPOSITORY_OWNER"),
                  webhook=webhook)
    except IssuesDisabled as exc:
        note = (f"GitHub Issues are disabled for {repo} ({exc}): {len(alerts)} alert(s) were NOT "
                "delivered as ops-alert issues; they are listed in this job summary. "
                "Enable Issues or set ALERT_WEBHOOK_URL to restore delivery.")
        print(f"::warning title=ops-alert channel down::{note}")
        if webhook:
            for a in alerts:
                try:
                    post_webhook(webhook, f"ALERT {a.title}")
                except Exception as wexc:  # noqa: BLE001
                    print(f"::warning title=ops-alert::webhook failed: {type(wexc).__name__}")
    except Exception as exc:  # noqa: BLE001 - alert delivery never fails the run
        note = f"Alert delivery failed: {type(exc).__name__}: {str(exc)[:300]}"
        print(f"::warning title=ops-alert::{note}")
    write_step_summary(alerts, note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
