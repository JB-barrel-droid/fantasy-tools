#!/usr/bin/env python3
"""Shared helpers for the source-pull watchdog (ops/watchdog/).

Deterministic, stdlib-only. No network except through fetch(); no writes
except the watchdog's own health.json.
"""
import json
import os
import re
import subprocess
from datetime import date, datetime, timezone

try:
    from zoneinfo import ZoneInfo
    CT = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover
    CT = None

HOME = os.path.expanduser("~")
WS = os.path.join(HOME, "workspace")
REPO = os.path.join(WS, "fantasy-tools")
GOAL = os.path.join(WS, "goals/football-signal-database-and-app")
FS = os.path.join(WS, "football-signal")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def now_ct():
    if CT is not None:
        return datetime.now(CT)
    return datetime.now(timezone.utc)


def today_ct():
    return now_ct().date()


def nfl_week(asof=None):
    """Current NFL week. 2026 season: Week 1 kicked off Thu Sep 10; weeks
    flip Thursday. (Same calendar rule as the pull scripts.)"""
    asof = asof or today_ct()
    kickoff = date(2026, 9, 10)
    wk = (asof - kickoff).days // 7 + 1
    return max(1, min(22, wk))


def fetch(url, timeout=60):
    """Fetch one URL via curl with a browser UA. Returns (status, body);
    (None, error-text) on curl failure."""
    try:
        p = subprocess.run(
            ["curl", "-sS", "-L", "-o", "-", "-w", "\n%{http_code}",
             "-A", UA, "--max-time", str(timeout), url],
            capture_output=True, text=True, timeout=timeout + 15)
    except Exception as e:
        return None, "curl exception: %s" % e
    out = p.stdout.rsplit("\n", 1)
    if len(out) != 2:
        return None, "curl output unparseable"
    body, code = out
    try:
        status = int(code.strip())
    except ValueError:
        return None, "curl bad status tail: %r" % code
    return status, body


def read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def mtime_utc(path):
    try:
        return datetime.fromtimestamp(os.stat(path).st_mtime,
                                      timezone.utc)
    except OSError:
        return None


def age_days(path, now=None):
    """Age of a file in days (fractional), measured in CT. None if missing."""
    mt = mtime_utc(path)
    if mt is None:
        return None
    now = now or now_ct()
    return (now - mt).total_seconds() / 86400.0


def is_today(path, now=None):
    """True if the file was modified today (CT)."""
    now = now or now_ct()
    mt = mtime_utc(path)
    if mt is None:
        return False
    return mt.astimezone(CT).date() == now.date() if CT else False


def classify_run_line(line):
    """Classify one pull-script runs-log line.

    Returns 'failed' | 'ok' | 'unchanged' | 'unknown'. The FAILED token is
    matched as a standalone status word so a player named e.g. 'Failed'
    can never trip it; SUCCESS/OK lines that say 'no update' / 'no-op' /
    'snapshot current' mean the source was unchanged (healthy, not a miss).
    """
    up = line.upper()
    if re.search(r"\bFAILED\b", up):
        return "failed"
    if re.search(r"\bNO UPDATE\b|\bNO-OP\b|SNAPSHOT CURRENT\b", up):
        return "unchanged"
    if re.search(r"\bSUCCESS\b|\|\s*OK\s*\|", up):
        return "ok"
    return "unknown"


def todays_run_lines(log_path, day=None):
    """(classified, raw_lines): today's runs-log lines for one pull script.

    classified is one of 'failed' | 'ok' | 'unchanged' | 'unknown' |
    'no-log' | 'did-not-run'. A day with both FAILED and later OK lines
    counts as ok (the retry succeeded); FAILED with no later success
    counts as failed.
    """
    day = day or today_ct()
    stamp = day.isoformat()
    try:
        with open(log_path) as f:
            lines = [ln for ln in f if ln.startswith(stamp)]
    except OSError:
        return "no-log", []
    if not lines:
        return "did-not-run", []
    states = [classify_run_line(ln) for ln in lines]
    if "failed" in states and "ok" not in states and "unchanged" not in states:
        return "failed", lines
    if "failed" in states:
        # failed then recovered the same day: healthy, but note the wobble
        return "ok", lines
    if "unchanged" in states:
        return "unchanged", lines
    if "ok" in states:
        return "ok", lines
    return "unknown", lines


def run_failed_time(log_path, day=None):
    """Timestamp (CT) of today's latest FAILED line, or None."""
    day = day or today_ct()
    stamp = day.isoformat()
    latest = None
    try:
        with open(log_path) as f:
            for ln in f:
                if ln.startswith(stamp) and classify_run_line(ln) == "failed":
                    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})", ln)
                    if m and CT is not None:
                        latest = datetime.strptime(
                            m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=CT)
    except OSError:
        pass
    return latest
