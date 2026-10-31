#!/usr/bin/env python3
"""JEG-1464: deterministic, read-only collection; writes only beneath --out.

Python 3.9+, gh's existing login, macOS for resource samples. No model calls.
All network collection uses `gh api --method GET` (GitHub REST).
"""
import argparse
import csv
import fcntl
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
FLOOR_KIB = 3_670_016  # Jeremy's job-specific override, 2026-10-31
DISK_PATH = "/Users/botcomp/code"
PROVIDERS = ("claude", "codex", "muse", "opencode", "pi")
CLAUDE_STATE = Path("/Users/botcomp/Documents/Codex/2026-10-30/co/work/bridge/state")
CODEX_STATE = Path.home() / "Library/Application Support/Code Bridge/Runtime/state/codex"
DEFAULT_JOURNALS = [("claude", CLAUDE_STATE / "job-journal.json"),
                    ("codex", CODEX_STATE / "job-journal.json")]
BASELINE = {"merged": 442, "median_h": 1.9, "p90_h": 19.4,
            "source": "JEG-1464 description, Muse Oct 17–31",
            "provenance": "UNCONFIRMED: original repo set, timezone, cutoff and percentile algorithm not supplied; scratch/rootcause/ absent on this Mac"}


class FloorError(RuntimeError):
    pass


def command(args):
    p = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if p.returncode:
        # Never relay stderr: remote messages or local paths can contain secrets.
        status = re.search(r"HTTP (\d{3})", p.stderr)
        category = " rate_limit" if "rate limit" in p.stderr.lower() else ""
        raise RuntimeError("command failed: " + args[0] + (" HTTP " + status[1] if status else "") + category)
    return p.stdout.strip()


def disk():
    fields = command(["df", "-k", DISK_PATH]).splitlines()[-1].split()
    return {"free_kib": int(fields[3]), "mount": fields[-1]}


def guard():
    sample = disk()
    if sample["free_kib"] < FLOOR_KIB:
        raise FloorError(f"disk floor: {sample['free_kib']} KiB on {sample['mount']}; minimum {FLOOR_KIB} KiB")
    return sample


def stamp(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def iso(value):
    return value.isoformat() if value else None


def bounds(day):
    # Calendar-day boundaries, including the 25-hour Nov 1 DST day.
    return (datetime.combine(day, time(), CT).astimezone(timezone.utc),
            datetime.combine(day + timedelta(days=1), time(), CT).astimezone(timezone.utc))


def hours(start, end):
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() / 3600, 4)


def stats(values):
    values = sorted(v for v in values if v is not None)
    return {"n": len(values), "median_h": statistics.median(values) if values else None,
            "p90_h": values[math.ceil(.9 * len(values)) - 1] if values else None,
            "worst_h": max(values) if values else None}


def approval_window(merged):
    local = merged.astimezone(CT)
    # Operational bins, not a claim of approval: [06:00,07:00), [16:00,17:00).
    return "06" if local.hour == 6 else "16" if local.hour == 16 else "outside"


class GitHub:
    def get(self, endpoint, **params):
        guard()
        if not (endpoint.startswith("repos/") or endpoint == "search/issues") or ".." in endpoint:
            raise ValueError("only GitHub repository REST endpoints are allowed")
        args = ["gh", "api", "--method", "GET", endpoint]
        for key, value in params.items():
            args.extend(["-f", f"{key}={value}"])
        return json.loads(command(args))

    def pages(self, endpoint, key=None, **params):
        rows = []
        page = 1
        while True:
            result = self.get(endpoint, per_page=100, page=page, **params)
            batch = result[key] if key else result
            rows.extend(batch)
            if len(batch) < 100:
                return rows
            page += 1

    def pulls(self, repo, since):
        rows = []
        page = 1
        while True:
            batch = self.get(f"repos/{repo}/pulls", state="all", sort="updated",
                             direction="desc", per_page=100, page=page)
            rows.extend(p for p in batch if stamp(p["updated_at"]) >= since)
            if len(batch) < 100 or any(stamp(p["updated_at"]) < since for p in batch):
                return rows
            page += 1

    def merged_search(self, repo, start, end):
        """Independent REST search allowance; explicit degraded collection mode."""
        rows = {}
        day = start
        while day <= end:
            a, b = bounds(day)
            page = 1
            while True:
                result = self.get("search/issues", q=f"repo:{repo} is:pr is:merged merged:{iso(a)}..{iso(b)}",
                                  per_page=100, page=page)
                if result.get("incomplete_results") or result["total_count"] > 1000:
                    raise RuntimeError("incomplete REST search result; refusing partial counts")
                for p in result["items"]:
                    merged = stamp(p.get("pull_request", {}).get("merged_at"))
                    if merged and a <= merged < b:
                        rows[p["number"]] = {"number": p["number"], "title": p["title"],
                            "created_at": p["created_at"], "merged_at": iso(merged), "state": "closed",
                            "head": {"sha": None, "ref": ""}, "base": {"repo": {"full_name": repo}}}
                if len(result["items"]) < 100:
                    break
                page += 1
            day += timedelta(days=1)
        return list(rows.values())


def first_all_green(checks, statuses):
    """Earliest simultaneous green of all observed contexts on this exact head.

    Includes reruns: a failed or pending later attempt invalidates green until
    it passes. Unknown/missing required checks are not inferred from this proxy.
    """
    events, names = [], set()
    for c in checks:
        name = "check:" + str(c.get("app", {}).get("id")) + ":" + c["name"]
        names.add(name)
        for when, good in [(c.get("started_at"), False),
                           (c.get("completed_at"), c.get("conclusion") in ("success", "neutral", "skipped"))]:
            if when:
                events.append((stamp(when), name, good))
    for s in statuses:
        name = "status:" + s["context"]
        names.add(name)
        events.append((stamp(s["created_at"]), name, s["state"] == "success"))
    state = {}
    for when in sorted(set(e[0] for e in events)):
        for t, name, good in events:
            if t == when:
                state[name] = good
        if names and all(state.get(n, False) for n in names):
            return when
    return None


def ticket_refs(p):
    return sorted(set(ref.upper() for ref in re.findall(r"\bJEG-\d+\b", " ".join(
        [p.get("title", ""), p.get("body") or "", p["head"].get("ref", "")]), re.I)))


def milestones(p, timeline, reviews, checks, statuses, ticket_data):
    opened, merged = stamp(p["created_at"]), stamp(p.get("merged_at"))
    refs = ticket_refs(p)
    starts, markers = [], []
    for ref in refs:
        t = ticket_data.get(ref, {})
        starts.extend(stamp(h["startedAt"]) for h in t.get("stateHistory", [])
                      if h.get("state", {}).get("type") == "started")
        markers.extend(stamp(m["at"]) for m in t.get("review_pass", [])
                       if m.get("head_sha") == p["head"]["sha"])
    requested = [stamp(e["created_at"]) for e in timeline
                 if e.get("event") in ("ready_for_review", "review_requested") and e.get("created_at")]
    if not p.get("draft") and not any(e.get("event") == "ready_for_review" for e in timeline):
        # A PR opened non-draft is reviewable from creation; first explicit
        # request remains separately visible in the receipt.
        ready = opened
    else:
        ready = min(requested, default=None)
    approvals = [stamp(r["submitted_at"]) for r in reviews if r["state"] == "APPROVED"]
    current = [stamp(r["submitted_at"]) for r in reviews
               if r["state"] == "APPROVED" and r.get("commit_id") == p["head"]["sha"]] + markers
    if merged:
        checks = [c for c in checks if c.get("started_at") and stamp(c["started_at"]) <= merged]
        statuses = [s for s in statuses if stamp(s["created_at"]) <= merged]
    green = first_all_green(checks, statuses)
    if merged and green and green > merged:
        green = None
    first_pass = min(approvals + markers, default=None)
    current_pass = min(current, default=None)
    # Observed gate proxy only: branch protection, dismissed approvals and
    # unrecorded Linear review markers can prevent true merge readiness.
    gate = max(ready, current_pass, green) if ready and current_pass and green else None
    if merged and gate and gate > merged:
        gate = None
    times = {"started": min(starts, default=None), "opened": opened,
             "review_requested": min(requested, default=None), "ready_for_review": ready,
             "review_passed": first_pass, "review_passed_head": current_pass,
             "ci_green_head": green, "merge_ready_proxy": gate, "merged": merged}
    pairs = {"started_to_open": (times["started"], opened),
             "open_to_review": (opened, ready), "review_to_pass": (ready, first_pass),
             "open_to_ci_green": (opened, green), "open_to_merge_ready_proxy": (opened, gate),
             "merge_ready_proxy_to_merge": (gate, merged), "open_to_merge": (opened, merged)}
    return {"repo": p["base"]["repo"]["full_name"], "pr": p["number"], "tickets": refs,
            "head_sha": p["head"]["sha"], "milestones": {k: iso(v) for k, v in times.items()},
            "wait_h": {k: hours(a, b) for k, (a, b) in pairs.items()}}


def load_json(path, default):
    return json.loads(Path(path).read_text()) if path and Path(path).exists() else default


def journal_data(journals):
    events, coverage = [], []
    seen = set()
    for provider, path in journals:
        if not path.exists():
            coverage.append(f"{provider}: journal unavailable")
            continue
        doc = load_json(path, {})
        for e in doc.get("events", []):
            key = (provider, e.get("event_id") or (e.get("run_id"), e.get("status"), e.get("created_at")))
            if key in seen:
                continue
            seen.add(key)
            # Whitelist only metadata. Never copy prompts, reports or comments.
            events.append({"provider": provider, "run_id": e.get("run_id"),
                           "session_id": e.get("session_id"), "at": e.get("created_at"),
                           "status": e.get("status"), "ticket": e.get("linear_issue")})
        coverage.append(f"{provider}: {len(doc.get('events', []))} journal events; completion-only, running/queued unknown")
    return events, coverage


def saved_usage(root):
    """Latest saved result per session; resumes may overwrite earlier results."""
    rows = []
    for path in sorted(root.glob("native*/sessions/*/result.json")):
        guard()
        doc = load_json(path, {})
        result = doc.get("result", {})
        if not isinstance(result, dict):
            continue
        usage = result.get("usage") or {}
        row = {"session_id": path.parent.name, "at": doc.get("createdAt")}
        for field in ("numTurns", "durationMs", "totalCostUsd"):
            row[field] = result.get(field)
        for field in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            row[field] = usage.get(field)
        rows.append(row)
    return rows


def usage_daily(events, usage, day):
    start, end = bounds(day)
    out = {}
    for provider in PROVIDERS:
        es = [e for e in events if e["provider"] == provider and e["at"] and start <= stamp(e["at"]) < end]
        jobs = len(set(e["run_id"] for e in es))
        us = [u for u in usage if u.get("at") and start <= stamp(u["at"]) < end] if provider == "claude" else []
        totals = {}
        for field in ("numTurns", "durationMs", "totalCostUsd", "input_tokens", "output_tokens",
                      "cache_read_input_tokens", "cache_creation_input_tokens"):
            values = [u[field] for u in us if isinstance(u.get(field), (int, float))]
            totals[field] = {"recorded_n": len(values), "sum": sum(values) if values else None}
        out[provider] = {"observed_run_ids": jobs if any(e["provider"] == provider for e in events) else None,
                         "failed_events": sum(e["status"] == "failed" for e in es) if any(e["provider"] == provider for e in events) else None,
                         "running": None, "queued": None, "saved_results_n": len(us), "usage": totals}
    return out


def resources():
    d = guard()
    row = {"at": iso(datetime.now(timezone.utc)), **d, "floor_kib": FLOOR_KIB}
    for field, args in [("ram_total_bytes", ["sysctl", "-n", "hw.memsize"]),
                        ("pressure_level", ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]),
                        ("cpu_count", ["sysctl", "-n", "hw.logicalcpu"])]:
        try:
            row[field] = int(command(args))
        except (RuntimeError, ValueError):
            row[field] = None
    try:
        row["load_1m"], row["load_5m"], row["load_15m"] = map(float, command(["sysctl", "-n", "vm.loadavg"]).strip("{} ").split())
        vm = command(["vm_stat"])
        page_size = int(re.search(r"page size of (\d+) bytes", vm).group(1))
        pages = {k: int(v) for k, v in re.findall(r"([^\n:]+):\s+(\d+)\.", vm)}
        # Active + wired + compressor physical pages; inactive cache excluded.
        row["ram_used_bytes"] = page_size * sum(pages.get(k, 0) for k in
            ("Pages active", "Pages wired down", "Pages occupied by compressor"))
    except (RuntimeError, ValueError, AttributeError):
        row["ram_used_bytes"] = None
    return row


def sample_open_prs(api, repos, captured):
    rows = []
    for repo in repos:
        for p in api.pages(f"repos/{repo}/pulls", state="open"):
            detail = api.get(f"repos/{repo}/pulls/{p['number']}")
            sha = detail["head"]["sha"]
            comparison = api.get(f"repos/{repo}/compare/{detail['base']['sha']}...{sha}")
            rows.append({"at": iso(captured), "repo": repo, "pr": p["number"],
                         "conflict": detail.get("mergeable") is False,
                         "mergeable_known": detail.get("mergeable") is not None,
                         "behind_by": comparison.get("behind_by")})
    return rows


def write_json(path, value):
    guard()
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def append_csv(path, rows):
    if not rows:
        return
    guard()
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def behind_hours(samples, repo, number, day):
    start, end = bounds(day)
    rows = sorted((r for r in samples if r["repo"] == repo and int(r["pr"]) == number), key=lambda r: r["at"])
    total, covered = 0, False
    for a, b in zip(rows, rows[1:]):
        t, u = stamp(a["at"]), stamp(b["at"])
        # Integrate bounded, consecutive observations only. Never stretch a
        # once-a-day sample across a day or extrapolate before first sample.
        if (u - t).total_seconds() > 600 or u <= start or t >= end:
            continue
        covered = True
        if a.get("behind_by", "") and int(a["behind_by"]) > 0:
            total += max(0, (min(u, end) - max(t, start)).total_seconds()) / 3600
    return round(total, 4) if covered else None


def take_sample(out, journals, activity_file=None):
    row = resources()
    append_csv(out / "capacity.csv", [row])
    events, _ = journal_data(journals)
    activity = load_json(activity_file, {})
    rows = []
    for provider in PROVIDERS:
        value = activity.get(provider, activity.get(provider + "_bridge", {}))
        # Do not refresh the timestamp on an old exported activity receipt.
        observed = stamp(activity.get("at"))
        fresh = observed and abs((stamp(row["at"]) - observed).total_seconds()) <= 300
        rows.append({"at": row["at"], "provider": provider,
                     "running": value.get("running") if fresh else None,
                     "queued": value.get("queued") if fresh else None,
                     "failed_events_total": sum(e["status"] == "failed" for e in events if e["provider"] == provider)
                     if any(e["provider"] == provider for e in events) else None})
    append_csv(out / "bridge-load.csv", rows)
    return row


def fmt(value):
    return "unknown" if value is None else f"{value:.2f}"


def daily(day, prs, receipts, events, usage, samples, asks, charter, captured):
    start, end = bounds(day)
    merged = [p for p in prs if p.get("merged_at") and start <= stamp(p["merged_at"]) < min(end, captured)]
    by_key = {(r["repo"], r["pr"]): r for r in receipts}
    rs = [by_key[(p["base"]["repo"]["full_name"], p["number"])] for p in merged]
    waits = {key: stats(r["wait_h"][key] for r in rs) for key in
             ("started_to_open", "open_to_review", "review_to_pass", "open_to_ci_green",
              "open_to_merge_ready_proxy", "merge_ready_proxy_to_merge", "open_to_merge")}
    # Rank disjoint stages only; cumulative open-to-merge would always win.
    stage_keys = ("started_to_open", "open_to_review", "review_to_pass", "merge_ready_proxy_to_merge")
    available = [k for k in stage_keys if waits[k]["median_h"] is not None]
    slowest = max(available, key=lambda k: waits[k]["median_h"]) if available else None
    counts = {key: sum(approval_window(stamp(p["merged_at"])) == key for p in merged) for key in ("06", "16", "outside")}
    conflict_rows = [s for s in samples if start <= stamp(s["at"]) < end]
    latest = max((s["at"] for s in conflict_rows), default=None)
    conflicts = [f"{s['repo']}#{s['pr']}" for s in conflict_rows if s["at"] == latest and s["conflict"] == "True"]
    unknown_mergeable = sum(s["at"] == latest and s.get("mergeable_known") == "False" for s in conflict_rows)
    behind = [{"repo": r["repo"], "pr": r["pr"], "tickets": r["tickets"],
               "sampled_behind_h": behind_hours(samples, r["repo"], r["pr"], day)} for r in receipts]
    ask_rows = [a for a in asks if start <= stamp(a["at"]) < end]
    ticket_waits = {}
    for ref in sorted({t for r in rs for t in r["tickets"]}):
        linked = [r for r in rs if ref in r["tickets"]]
        ticket_waits[ref] = {"prs": [r["pr"] for r in linked], "waits": {
            key: stats(r["wait_h"][key] for r in linked) for key in waits}}
    return {"date": str(day), "partial": captured < end, "merged": len(merged),
            "merge_time": stats(hours(stamp(p["created_at"]), stamp(p["merged_at"])) for p in merged),
            "windows": counts, "waits": waits, "slowest_observed_stage": slowest,
            "conflicts_as_of": latest, "open_conflicts": conflicts if latest else None,
            "mergeability_unknown_n": unknown_mergeable if latest else None,
            "usage": usage_daily(events, usage, day), "behind": behind,
            "asks": len({a["id"] for a in ask_rows}) if asks else None,
            "charter": charter, "prs": rs, "ticket_waits": ticket_waits,
            "open_prs_at_collection": [r for r in receipts if not r["milestones"]["merged"]]}


def markdown(report, coverage):
    s = report
    lines = [f"# Efficiency scorecard — {s['date']} (America/Chicago)", "",
             f"Slowest observed stage: **{s['slowest_observed_stage'] or 'unknown'}** (median among disjoint observed stages; missing stages can change ranking).", "",
             f"{'Partial day' if s['partial'] else 'Complete day'}; captured by this run. Baseline quoted: **442 merged, median 1.9 h, p90 19.4 h** (Muse Oct 17–31).",
             BASELINE["provenance"] + ". No causal payoff claim.", "",
             f"Merged: **{s['merged']}**; open → merge median **{fmt(s['merge_time']['median_h'])} h**, p90 **{fmt(s['merge_time']['p90_h'])} h**.",
             f"Merge time bins: 06:00–07:00 CT {s['windows']['06']}; 16:00–17:00 CT {s['windows']['16']}; outside {s['windows']['outside']}. These are bins, not recorded approvals.",
             f"Open conflicts: {', '.join(s['open_conflicts']) or '0' if s['open_conflicts'] is not None else 'unknown'}; mergeability unknown for {s['mergeability_unknown_n']} PRs; snapshot {s['conflicts_as_of'] or 'unavailable (no historical reconstruction)'}. Jeremy asks: {s['asks'] if s['asks'] is not None else 'unknown; coordinator must log asks.jsonl' }.", "",
             "| Stage | n | Median h | Worst h |", "|---|---:|---:|---:|"]
    for key, value in s["waits"].items():
        lines.append(f"| {key} | {value['n']} | {fmt(value['median_h'])} | {fmt(value['worst_h'])} |")
    lines += ["", "Merge-ready is an observed proxy (ready + exact-head approval + all observed CI contexts green), not proof of branch-rule eligibility. CI timestamps are on the merged PR head, never the squash commit. Behind-main durations are bounded sampled observations; no pre-sample history is inferred.", "",
              "| Provider | Observed journal run IDs | Failed events | Saved usage results | Turns (recorded n) | List-equivalent USD (recorded n) |", "|---|---:|---:|---:|---:|---:|"]
    for provider, u in s["usage"].items():
        turns, dollars = u["usage"]["numTurns"], u["usage"]["totalCostUsd"]
        lines.append(f"| {provider} | {u['observed_run_ids']} | {u['failed_events']} | {u['saved_results_n']} | {turns['sum']} ({turns['recorded_n']}) | {dollars['sum']} ({dollars['recorded_n']}) |")
    lines += ["", "None/unknown means unavailable, not zero. Saved Claude counters cover latest retained results only; resumes can overwrite earlier usage. Dollars are list-equivalent, never subscription spend. Codex/Muse/OpenCode/Pi tokens are unavailable unless a ledger supplies them. Running/queued counts require fresh exported get_bridge_activity observations; completion journals alone cannot measure occupancy.", "", "## Charter observations", "",
              "| Item | Shipped | Go-live | Intended metric | Observed change |", "|---|---|---|---|---|"]
    for c in s["charter"]:
        lines.append(f"| {c['ticket']} | {c.get('shipped', 'unknown')} | {c.get('go_live') or 'unknown'} | {c['metric']} | {c.get('observed_change', 'unknown; no comparable post-go-live cohort')} |")
    lines += ["", "Per-PR/ticket timestamps and waits: `" + s["date"] + ".json`; one PR can link multiple tickets and is counted once in PR aggregates. Capacity: `capacity.csv`; bridge: `bridge-load.csv`; open-head samples: `pr-samples.csv`.", "", "Coverage:", ""]
    lines += ["- " + item for item in coverage]
    return "\n".join(lines) + "\n"


def run(args, out, journals):
    captured = datetime.now(timezone.utc)
    start = date.fromisoformat(args.start) if args.start else captured.astimezone(CT).date() - timedelta(days=1)
    end = date.fromisoformat(args.end) if args.end else start
    if start > end or end > date(2026, 11, 13):
        raise ValueError("invalid date range; collection ends Nov 13, 2026")
    api = GitHub()
    since = bounds(min(start, date(2026, 10, 17)))[0]
    prs = []
    for repo in args.repo or ["JB-barrel-droid/fantasy-tools"]:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("invalid repo")
        if args.summary_only:
            prs.extend(api.merged_search(repo, min(start, date(2026, 10, 17)), end))
        else:
            prs.extend(api.pulls(repo, since))
    tickets = load_json(args.linear, {})
    events, coverage = journal_data(journals)
    usage = saved_usage(CLAUDE_STATE)
    coverage += ["Linear state history: supplied export" if tickets else "Linear state history unavailable under REST-only collection; supply --linear export. Linear GraphQL is never called.",
                 "scratch/rootcause/ missing on this Mac; no original baseline query to reuse.",
                 "Open conflicts and behind-main are sample-time facts only; Oct 30 history cannot be recovered from today's PR state."]
    if args.summary_only:
        coverage.append("Explicit --summary-only REST search run: core quota exhausted (0/5000). PR counts and merge times measured; timeline, CI, approvals, conflicts and head SHA unavailable.")
    receipts, open_samples = [], []
    for p in prs:
        merged = stamp(p.get("merged_at"))
        if not (p["state"] == "open" or merged and bounds(start)[0] <= merged < bounds(end)[1]):
            continue
        repo, number = p["base"]["repo"]["full_name"], p["number"]
        if args.summary_only:
            r = milestones(p, [], [], [], [], tickets)
            r["milestones"]["ready_for_review"] = None
            r["wait_h"]["open_to_review"] = None
            receipts.append(r)
            continue
        endpoint = f"repos/{repo}"
        print(f"Collecting {repo}#{number}", file=sys.stderr, flush=True)
        detail = api.get(f"{endpoint}/pulls/{number}")
        timeline = api.pages(f"{endpoint}/issues/{number}/timeline")
        reviews = api.pages(f"{endpoint}/pulls/{number}/reviews")
        sha = detail["head"]["sha"]
        checks = api.pages(f"{endpoint}/commits/{sha}/check-runs", key="check_runs", filter="all")
        statuses = api.pages(f"{endpoint}/commits/{sha}/statuses")
        receipts.append(milestones(detail, timeline, reviews, checks, statuses, tickets))
        if p["state"] == "open":
            comparison = api.get(f"{endpoint}/compare/{detail['base']['sha']}...{sha}")
            open_samples.append({"at": iso(captured), "repo": repo, "pr": number,
                                 "conflict": detail.get("mergeable") is False,
                                 "mergeable_known": detail.get("mergeable") is not None,
                                 "behind_by": comparison.get("behind_by")})
    append_csv(out / "pr-samples.csv", open_samples)
    take_sample(out, journals, args.activity)
    samples = read_csv(out / "pr-samples.csv")
    # A reproducible candidate baseline, kept separate from Muse's quote.
    baseline_start, baseline_end = bounds(date(2026, 10, 17))[0], min(bounds(date(2026, 10, 31))[1], captured)
    baseline_prs = [p for p in prs if p.get("merged_at") and baseline_start <= stamp(p["merged_at"]) < baseline_end]
    baseline = {"quoted": BASELINE, "recount": {"start_inclusive": iso(baseline_start),
                "end_exclusive": iso(baseline_end), "timezone": "America/Chicago",
                "repos": args.repo or ["JB-barrel-droid/fantasy-tools"],
                "unit": "one merged PR number per repo; filter merged_at, not created_at; all authors and base branches; drafts included",
                "duration": "created_at to merged_at, elapsed wall hours; never ready-for-review",
                "p90": "nearest rank, sorted[ceil(0.9*n)-1]; median averages middle pair",
                "n": len(baseline_prs), "stats": stats(hours(stamp(p["created_at"]), stamp(p["merged_at"])) for p in baseline_prs),
                "pr_numbers": sorted(f"{p['base']['repo']['full_name']}#{p['number']}" for p in baseline_prs)}}
    write_json(out / "baseline.json", baseline)
    asks = []
    if args.asks and Path(args.asks).exists():
        asks = [json.loads(line) for line in Path(args.asks).read_text().splitlines() if line.strip()]
    charter = load_json(args.charter, [])
    # Never show today's live state as if it had been live on earlier dates.
    daily_rows = read_csv(out / "daily.csv")
    day = start
    while day <= end:
        historical_charter = []
        for item in charter:
            item = dict(item)
            live = stamp(item.get("go_live"))
            if live and live >= bounds(day)[1]:
                item.update(shipped=False, go_live=None, observed_change="not live in this window")
            historical_charter.append(item)
        report = daily(day, prs, receipts, events, usage, samples, asks, historical_charter, captured)
        write_json(out / f"{day}.json", report)
        guard()
        (out / f"{day}.md").write_text(markdown(report, coverage))
        row = {"date": str(day), "partial": report["partial"], "merged": report["merged"],
               "median_h": report["merge_time"]["median_h"], "p90_h": report["merge_time"]["p90_h"],
               "window_06": report["windows"]["06"], "window_16": report["windows"]["16"],
               "outside": report["windows"]["outside"], "open_conflicts": len(report["open_conflicts"]) if report["open_conflicts"] is not None else None,
               "asks": report["asks"]}
        # One row/date, idempotent reruns update partial days instead of duplicating.
        daily_rows = [r for r in daily_rows if r["date"] != str(day)] + [row]
        day += timedelta(days=1)
    guard()
    with (out / "daily.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerows(sorted(daily_rows, key=lambda r: r["date"]))
    if end == date(2026, 11, 13):
        guard()
        (out / "final-summary.md").write_text("# Final observed scorecard through Nov 13\n\n" +
            "Baseline and per-day measures: baseline.json and daily.csv. Changes are observations, not causal estimates.\n\n" +
            "\n".join(f"- {r['date']}: {r['merged']} merged; median {r['median_h']} h; p90 {r['p90_h']} h" for r in sorted(daily_rows, key=lambda r: r["date"])))
    print(json.dumps({"dates": [str(start), str(end)], "baseline_recount_n": len(baseline_prs), "disk": guard()}))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "sample"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--start", help="inclusive CT calendar date; default yesterday")
    parser.add_argument("--end", help="inclusive CT calendar date; default start")
    parser.add_argument("--repo", action="append")
    parser.add_argument("--journal", action="append", default=[], help="provider=/path/job-journal.json")
    parser.add_argument("--linear", help="allowlisted ticket state-history export JSON")
    parser.add_argument("--charter", help="charter go-live observations JSON")
    parser.add_argument("--asks", help="coordinator ask log JSONL, one id/at per ask")
    parser.add_argument("--activity", help="fresh timestamped get_bridge_activity export JSON")
    parser.add_argument("--sample-prs", action="store_true", help="also sample open conflicts and behind main (REST)")
    parser.add_argument("--summary-only", action="store_true", help="explicit REST-search-only counts and merge times; stage data unknown")
    args = parser.parse_args(argv)
    try:
        guard()  # before mkdir, lock, any API call, or output write
        args.out.mkdir(parents=True, exist_ok=True)
        journals = list(DEFAULT_JOURNALS)
        for entry in args.journal:
            provider, path = entry.split("=", 1)
            if provider not in PROVIDERS:
                raise ValueError("unknown provider")
            journals.append((provider, Path(path)))
        # Nonblocking output lock: never overlap writers or queue a retry.
        with (args.out / ".scorecard.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.mode == "sample":
                if datetime.now(CT).date() > date(2026, 11, 13):
                    return 0
                take_sample(args.out, journals, args.activity)
                if args.sample_prs:
                    append_csv(args.out / "pr-samples.csv", sample_open_prs(GitHub(), args.repo or ["JB-barrel-droid/fantasy-tools"], datetime.now(timezone.utc)))
            else:
                if not args.start and datetime.now(CT).date() > date(2026, 11, 14):
                    return 0
                run(args, args.out, journals)
        return 0
    except FloorError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except (RuntimeError, ValueError, OSError, KeyError, subprocess.TimeoutExpired) as exc:
        detail = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        print("scorecard stopped: " + detail + "; no retry performed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
