#!/usr/bin/env python3
"""What "late" means for each source, checked hourly, loudly (JEG-1200, JEG-1201).

Jeremy, 2026-10-28: "dynamic sources should update daily, and never late for
a week." And: "Projection sources update constantly, so they should never be
delayed. So does fantasycalc. Trade chart articles tend to publish at the
same time every week. We should organize on a source by source basis, make
checks for the data lightweight."

On Oct 28 the board sat on week 7 for about 44 hours and nothing reached
Jeremy; the probes also logged nothing at all on Oct 20 and 21 (a Tuesday,
when every trade chart publishes) and FantasySharks has failed every ingest
since at least Oct 22. Each of those is "late" under one of the rules below.

Every source has its own rule (RULES). Three lightweight checks, all read
from what already exists (public.source_probe_state, written by
source_probe.py on every probe, and the week each source serves on the site,
data/history/index.json); nothing here fetches a source:

    probe_silent      the source's probe has not run for longer than its
                      probe_gap (its probe schedule, doubled, plus slack)
    refresh_failing   the newest data we hold was last confirmed current
                      longer ago than late_after. "Confirmed current" is the
                      last probe when that probe read the source and saw the
                      content the last good ingest saved; otherwise it is the
                      last good ingest. So a changed source that never gets
                      saved, or a source the probe cannot read, goes late.
    week_late         live sources: the site still serves the previous week
                      after the week's switch time. Weekly articles: after the
                      article's due time the probe still sees last week's
                      article (the publisher is late), or it sees the new one
                      and the site still serves last week (we are late).

Late sources open one GitHub issue labelled `source-late` (comments at most
every COMMENT_HOURS while it stays open, sooner when the late set changes)
and it closes itself when every source is on time again. GitHub emails the
repository owner. A late source never fails a job or changes a value;
an incomplete check or failed alert delivery fails the monitoring run.

    python3 pipelines/source_lateness.py [--state-file F | --supabase] [--out F] [--alert]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import nfl_week  # noqa: E402
from lib.timestamps import parse_iso_timestamp  # noqa: E402

CT = ZoneInfo("America/Chicago")
H = timedelta(hours=1)
HISTORY = REPO / "data" / "history" / "index.json"
CHAIN_STATUS = REPO / "output" / "comparison-chain-status.json"
LABEL = "source-late"
TITLE = "A data source is late"
COMMENT_HOURS = 6
API = "https://api.github.com"


@dataclass(frozen=True)
class Rule:
    """kind: live (changes all week; never delayed), weekly (one article a
    week at a steady time) or reference (feeds a check, not the chart).
    due: (days after the content week's Tuesday, hour CT) by which the week's
    data must be on hand. probe_gap / late_after: see the module docstring."""
    kind: str
    on_site: bool
    probe_gap: timedelta
    late_after: timedelta
    due: tuple[int, int] | None
    usual: str


RULES: dict[str, Rule] = {
    # Live sources, never delayed. FantasyCalc is probed hourly and a change
    # is saved at most every 6 h (source_probe POLICIES min_interval).
    # Projections are probed every 4 h (source-probe-projections).
    # Their freshness is the late_after check. The week label is due
    # Wednesday 12:00 CT: unchanged content gets its first new-week save only
    # at the 20 h max-age re-ingest (CBS ROS weeks 5-6: Monday 19:25 UTC
    # saves), so Tuesday noon would cry wolf every week (PR #1042 review).
    "fantasycalc": Rule("live", True, 3 * H, 9 * H, (1, 12), "changes all day; saved at most every 6 hours"),
    "espn": Rule("live", True, 9 * H, 9 * H, (1, 12), "projections change all week"),
    "cbsros": Rule("live", True, 9 * H, 9 * H, (1, 12), "projections change all week"),
    "razzball": Rule("live", True, 9 * H, 9 * H, (1, 12), "projections change all week"),
    # Weekly trade-chart articles. Probed every 3 h Mon-Thu, every 12 h
    # Fri-Sun. First seen (probe log and the articles' own dates, weeks 5-8,
    # 2026): FantasyPros Tue 8-11 AM CT; USA Today Tue 1-4 PM CT; CBS Tue
    # 4-5 PM CT. Due Wednesday 12:00 CT: the latest observed time plus most of
    # a day, and still a day before the Thursday 12:00 CT stale flag (JEG-1180).
    "fantasypros": Rule("weekly", True, 13 * H, 26 * H, (1, 12), "publishes Tuesday morning"),
    "usatoday": Rule("weekly", True, 13 * H, 26 * H, (1, 12), "publishes Tuesday afternoon"),
    "cbs": Rule("weekly", True, 13 * H, 26 * H, (1, 12), "publishes Tuesday afternoon"),
    # Reference pages for the fidelity checks, probed twice a day.
    "draftsharks": Rule("reference", False, 26 * H, 36 * H, None, "moves a few times a week"),
    "fantasysharks": Rule("reference", False, 26 * H, 36 * H, None, "moves a few times a week"),
}

NAMES = {"fantasycalc": "FantasyCalc", "espn": "ESPN", "cbsros": "CBS rest of season",
         "razzball": "Razzball", "fantasypros": "FantasyPros", "usatoday": "USA Today",
         "cbs": "CBS", "draftsharks": "DraftSharks", "fantasysharks": "FantasySharks"}


def _ts(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = parse_iso_timestamp(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hours(delta: timedelta) -> str:
    h = delta.total_seconds() / 3600
    return f"{h:.0f} hours" if h < 48 else f"{h / 24:.1f} days"


def due_at(rule: Rule, week: int) -> datetime | None:
    """The instant content week `week`'s data is due for this source."""
    if rule.due is None:
        return None
    days, hour = rule.due
    day = nfl_week.content_week_start(week) + timedelta(days=days)
    return datetime.combine(day, time(hour), tzinfo=CT)


def confirmed_current_at(row: dict[str, Any]) -> datetime | None:
    """When the data we hold was last known to be the source's current data."""
    acked = _ts(row.get("acked_at"))
    probe = _ts(row.get("last_probe_at"))
    fp = row.get("last_fp")
    if row.get("last_ok") and fp and fp == row.get("acked_fp") and probe:
        return max(probe, acked) if acked else probe
    return acked


def seen_week(row: dict[str, Any]) -> int | None:
    """The newest article week the probe saw (weekly sources record it)."""
    week = (row.get("last_signals") or {}).get("week") if isinstance(row.get("last_signals"), dict) else None
    return week if isinstance(week, int) and not isinstance(week, bool) else None


def judge(source: str, row: dict[str, Any] | None, served: int | None, now: datetime) -> dict[str, Any]:
    """One source's verdict at `now`: {late, reasons[], ...}. Pure."""
    rule = RULES[source]
    row = row or {}
    name = NAMES.get(source, source)
    week = nfl_week.content_week(nfl_week.today_ny(now))
    reasons: list[str] = []

    probe = _ts(row.get("last_probe_at"))
    if probe is None or now - probe > rule.probe_gap:
        reasons.append(f"its change check has not run for {_hours(now - probe)}" if probe else
                       "its change check has never run")

    confirmed = confirmed_current_at(row)
    if confirmed is None or now - confirmed > rule.late_after:
        why = (f"; the last check failed: {str(row.get('last_error')).strip()[:120]}"
               if row.get("last_ok") is False and row.get("last_error") else "")
        reasons.append((f"our copy was last confirmed current {_hours(now - confirmed)} ago"
                        if confirmed else "we have never saved it") + why)

    due = due_at(rule, week)
    # Week checks run only inside the content week: after week 18 the week
    # stays 18, and an offseason with no new charts must not hold the alert.
    in_week = now.astimezone(CT).date() < nfl_week.content_week_start(week) + timedelta(days=7)
    if due is not None and now >= due and week > 1 and in_week:
        if rule.kind == "weekly":
            seen = seen_week(row)
            if isinstance(seen, int) and seen < week:
                reasons.append(f"it has not published its week {week} chart ({rule.usual}); "
                               f"the newest is week {seen}")
            elif rule.on_site and isinstance(served, int) and served < week:
                reasons.append(f"its week {week} chart is out but the site still shows week {served}")
        elif rule.on_site and isinstance(served, int) and served < week:
            reasons.append(f"the site still shows its week {served} data")

    return {"source": source, "name": name, "kind": rule.kind, "on_site": rule.on_site,
            "usual": rule.usual, "late": bool(reasons), "reasons": reasons,
            "confirmed_current_at": confirmed.isoformat() if confirmed else None,
            "last_probe_at": probe.isoformat() if probe else None,
            "served_week": served, "seen_week": seen_week(row), "content_week": week,
            "due_at": due.isoformat() if due else None}


def known_week(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def served_weeks(history: dict[str, Any], status: dict[str, Any]) -> dict[str, int]:
    """The week each source serves on the site: the history index (what is
    published), else the chain status' last run."""
    out: dict[str, int] = {}
    for src, info in (status.get("source_weeks") or {}).items():
        wk = info.get("served_week") if isinstance(info, dict) else None
        if known_week(wk):
            out[src] = wk
    for src, info in (history.get("served") or {}).items():
        wk = info.get("week") if isinstance(info, dict) else None
        if known_week(wk):
            out[src] = wk
        else:
            # An explicit unknown in the published index must not become
            # "current" via a chain attempt that may never have published.
            out.pop(src, None)
    return out


def report(state: dict[str, dict[str, Any]], history: dict[str, Any], status: dict[str, Any],
           now: datetime) -> dict[str, Any]:
    served = served_weeks(history, status)
    rows = [judge(src, state.get(src), served.get(src), now) for src in RULES]
    return {"schema": "source-lateness-v1", "checked_at": now.isoformat(),
            "content_week": nfl_week.content_week(nfl_week.today_ny(now)),
            "late": [r["source"] for r in rows if r["late"]],
            "unknown_served_weeks": [r["source"] for r in rows
                                     if r["on_site"] and not known_week(r["served_week"])],
            "sources": {r["source"]: r for r in rows}}


def body(rep: dict[str, Any]) -> str:
    late = [rep["sources"][s] for s in rep["late"]]
    lines = [f"{len(late)} source{'s' if len(late) != 1 else ''} late "
             f"(content week {rep['content_week']}, checked {rep['checked_at'][:16]}Z):", ""]
    for r in late:
        where = "" if r["on_site"] else " (fidelity reference, not on the chart)"
        lines.append(f"- **{r['name']}**{where}: " + "; ".join(r["reasons"]) + ".")
    lines += ["", "What late means for each source and what to do: docs/source-lateness.md."]
    run, repo = os.environ.get("GITHUB_RUN_ID"), os.environ.get("GITHUB_REPOSITORY")
    if run and repo:
        lines += [f"Latest check: https://github.com/{repo}/actions/runs/{run}"]
    lines += ["", "This issue closes itself when every source is on time again (JEG-1200)."]
    return "\n".join(lines)


def _call(method: str, path: str, token: str, payload: dict | None = None):
    req = urllib.request.Request(
        API + path, method=method,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def _late_marker(rep: dict[str, Any]) -> str:
    return "<!-- late: " + ",".join(sorted(rep["late"])) + " -->"


def alert(rep: dict[str, Any], repo: str | None, token: str | None, now: datetime, call=None) -> str:
    """Open, comment on or close the source-late issue; returns what it did."""
    if rep.get("unknown_served_weeks"):
        raise ValueError("served week unknown for " + ", ".join(rep["unknown_served_weeks"]))
    late = bool(rep["late"])
    if not token or not repo:
        return (f"dry run: would open or update the {LABEL} issue\n{body(rep)}" if late
                else f"dry run: no source late; would close any open {LABEL} issue")
    call = call or _call
    issues = call("GET", f"/repos/{repo}/issues?state=open&per_page=100", token) or []
    issues = [i for i in issues if "pull_request" not in i and (
        i.get("title") == TITLE or LABEL in {(lb or {}).get("name") for lb in i.get("labels") or []})]
    issue = issues[0] if issues else None
    if not late:
        if not issue:
            return "every source on time; no open issue"
        call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token,
             {"body": "Every source is on time again, so this is resolved."})
        call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token,
             {"state": "closed", "state_reason": "completed"})
        return f"closed #{issue['number']}"
    text = body(rep) + "\n" + _late_marker(rep)
    if issue is None:
        made = call("POST", f"/repos/{repo}/issues", token, {"title": TITLE, "body": text, "labels": [LABEL]})
        return f"opened #{made['number']}"
    since = _ts(issue.get("updated_at"))
    changed = _late_marker(rep) not in (issue.get("body") or "")
    if not changed and since is not None and now - since < timedelta(hours=COMMENT_HOURS):
        return f"#{issue['number']} already open; updated {_hours(now - since)} ago"
    call("PATCH", f"/repos/{repo}/issues/{issue['number']}", token, {"body": text})
    call("POST", f"/repos/{repo}/issues/{issue['number']}/comments", token, {"body": body(rep)})
    return f"updated #{issue['number']}"


def _read(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_state(args) -> dict[str, dict[str, Any]]:
    if args.supabase:
        import sbclient  # the gh_sbclient shim in CI
        return {r["source"]: r for r in sbclient.get("source_probe_state", "?select=*") or []}
    return _read(Path(args.state_file)) if args.state_file else {}


def summary_lines(rep: dict[str, Any]) -> list[str]:
    out = ["| Source | Kind | On time | Why |", "|---|---|---|---|"]
    for r in rep["sources"].values():
        unknown = r["source"] in rep.get("unknown_served_weeks", [])
        on_time = "no" if r["late"] else "unknown" if unknown else "yes"
        reasons = r["reasons"] + (["served week unknown"] if unknown else [])
        out.append(f"| {r['name']} | {r['kind']} | {on_time} | "
                   f"{'; '.join(reasons) or r['usual']} |")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--supabase", action="store_true", help="read public.source_probe_state")
    src.add_argument("--state-file", help="probe state JSON (source_probe.py FileStore format)")
    ap.add_argument("--history", default=str(HISTORY))
    ap.add_argument("--status", default=str(CHAIN_STATUS))
    ap.add_argument("--out", help="write the report JSON here")
    ap.add_argument("--alert", action="store_true", help="open/update/close the source-late issue")
    args = ap.parse_args(argv)
    now = nfl_week.now_utc()
    try:
        rep = report(load_state(args), _read(Path(args.history)), _read(Path(args.status)), now)
    except Exception as e:  # noqa: BLE001
        # A late source never fails the job (the issue is the alert), but a
        # watchdog that cannot run must not go quiet: fail the run so it shows.
        print(f"::error title=source lateness::not checked ({type(e).__name__}: {e})")
        return 1
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n")
    for s in rep["late"]:
        r = rep["sources"][s]
        print(f"::warning title={r['name']} late::" + "; ".join(r["reasons"])[:900])
    if not rep["late"] and not rep["unknown_served_weeks"]:
        print("source lateness: every source on time")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("## Source lateness (JEG-1200)\n\n" + "\n".join(summary_lines(rep)) + "\n")
    if rep["unknown_served_weeks"]:
        print("::error title=source lateness::not checked: served week unknown for "
              + ", ".join(rep["unknown_served_weeks"]) + "; existing alerts left unchanged")
        return 1
    if args.alert:
        try:
            print("source lateness alert: " + alert(rep, os.environ.get("GITHUB_REPOSITORY"),
                                                     os.environ.get("GITHUB_TOKEN"), now))
        except Exception as e:  # noqa: BLE001
            print(f"::error title=source lateness alert::alert failed ({type(e).__name__}: {e})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
