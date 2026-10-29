#!/usr/bin/env python3
"""JEG-621: pull Fantasy Sharks public rest-of-season projections -> snapshot.json.

Source (public, no login, no paywall; measured 2026-10-15, HTTP 200):
  https://www.fantasysharks.com/apps/bert/forecasts/projections.php
    ?Segment=877 (2026 Rest of Year) &Position=97 (All Offense) &scoring=<id>
    &csv=1 for the CSV the page itself links (the CSV icon), no csv for the HTML
Scoring ids (Fantasy Sharks "Default" sets): 1 non-PPR, 18 half-PPR, 2 PPR.
The CSV carries Player ID, Player Name ("Last, First"), Team, Position and Pts
(rest-of-year fantasy points). It carries NO vintage, so the HTML page (half-PPR
request) is read for "Last updated MM-DD" and for the selected Period and
Position, which pins that Segment 877 is still the rest-of-year period.

What Fantasy Sharks does NOT publish: there is no public trade value chart (the
Trade Coach is an interactive tool, not a table) and no per-game figure for the
rest-of-year period, only the total Pts. Weekly (Segment 883-900) and
rest-of-career (99200) periods exist on the same endpoint; only rest-of-year is
pulled here, because that is the input the chart consumes.

Weekly mode (--period weekly, JEG-621 2026-10-29): the same endpoint and CSV for
the current content week's Segment, found by its "Week N" label in the page's
own Period list (never a hard-coded id). It writes a separate snapshot
(schema fantasysharks_weekly_v1, source fantasysharks_weekly, with "week") that
the rest-of-year saver refuses: weekly and rest-of-year data are never blended.
Weekly is held: no table, no saver, nothing reads it yet.

Transport (GAP-FANTASYSHARKS-CI-BLOCKED, 2026-10-29): Fantasy Sharks answers
HTTP 403 to GitHub-hosted runners (every sync run since 2026-10-19). On a
401/402/403/429 the fetch is retried once through the Supabase Edge Function
`fantasysharks-fetch` (service role only, allowlisted to this one path; same
pattern as the USA Today relay), which returns the upstream status verbatim,
so every check below is unchanged. With no SUPABASE_URL/SUPABASE_SERVICE_KEY,
or a non-200 from the relay, the pull still fails SOURCE_BLOCKED.

robots.txt asks for Crawl-delay 60 for all agents. Jeremy waived legal/ToS review
(2026-10-12) but the puller still makes only four requests and waits --delay
seconds (default 5) between them.

Output: <out-dir>/snapshot.json
  {"schema", "source", "source_url", "segment", "fetched_at", "vintage_date",
   "fingerprint", "rows": [{player_name, player_norm, pos, team, fantasysharks_id,
   pts: {non_ppr, half_ppr, ppr}}], "row_count", "dropped"}
A Pts of 0 means unprojected and is written null, never 0. Identity (player_key)
is resolved later by the saver against public.players via lib/canonical_players.

Fail closed (non-zero exit, no snapshot written), named on the
`FANTASYSHARKS PULL FAILED [CODE]` line:
  SOURCE_BLOCKED    non-200, login redirect, non-CSV body
  SOURCE_LAYOUT     header column gone, Period/Position no longer rest-of-year /
                    All Offense, no "Last updated" stamp
  SOURCE_TRUNCATED  a position below its row floor
  VALUE_RANGE       Pts outside -50..500, or scoring sets out of order
                    (PPR < half-PPR < non-PPR for a player is a mixed-up scoring)
  SOURCE_STALE      "Last updated" more than --max-age-days old
"""
from __future__ import annotations

import argparse
import csv
import os
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402
from nfl_week import content_week  # noqa: E402

BASE = "https://www.fantasysharks.com/apps/bert/forecasts/projections.php"
SEGMENT = 877
POSITION = 97
SCORINGS = {"non_ppr": 1, "half_ppr": 18, "ppr": 2}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
POSITIONS = ("QB", "RB", "WR", "TE")
# about 40% of the 2026-10-15 counts (QB 71, RB 126, WR 174, TE 112)
ROW_FLOORS = {"QB": 28, "RB": 50, "WR": 70, "TE": 45}
REQUIRED_COLUMNS = ("Player ID", "Player Name", "Team", "Position", "Pts")
PTS_RANGE = (-50.0, 500.0)
SCHEMA = "fantasysharks_ros_v1"
MAX_AGE_DAYS = 10
ROS_LABEL = r"\d{4} Rest of Year"

# Weekly period (held; separate snapshot, never blended with rest-of-year).
WEEKLY_SCHEMA = "fantasysharks_weekly_v1"
WEEKLY_SOURCE = "fantasysharks_weekly"
# about 40% of a full week's skill-position list less byes (no live count yet)
WEEKLY_ROW_FLOORS = {"QB": 20, "RB": 35, "WR": 50, "TE": 30}
WEEKLY_PTS_RANGE = (-10.0, 70.0)
WEEKLY_MAX_AGE_DAYS = 8
WEEK_OPTION_RE = re.compile(
    r'<option value="?(\d+)"?[^>]*>\s*(?:\d{4}\s+)?(?:NFL\s+)?Week\s+(\d+)\s*</option>', re.I)

RELAY_FUNCTION = "fantasysharks-fetch"
BLOCK_STATUSES = (401, 402, 403, 429)


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def url_for(scoring_id: int, csv_out: bool, segment: int = SEGMENT) -> str:
    q = f"Segment={segment}&Position={POSITION}&scoring={scoring_id}"
    return f"{BASE}?csv=1&{q}" if csv_out else f"{BASE}?{q}"


def fetch_via_relay(url: str, timeout: int = 90):
    """GET `url` through the Supabase Edge Function `fantasysharks-fetch`.

    Returns (status, body) with the upstream status verbatim, or None when the
    relay is not configured or unreachable (then the direct failure stands)."""
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        return None
    req = urllib.request.Request(
        f"{base}/functions/v1/{RELAY_FUNCTION}",
        data=json.dumps({"url": url}).encode(), method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key, "apikey": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001 - any relay failure = no relay
        print(f"[fantasysharks] relay unavailable: {e}", file=sys.stderr, flush=True)
        return None
    if not isinstance(d, dict) or "status" not in d:
        return None
    return d["status"], d.get("body") or ""


def _direct(url: str):
    """(status, final_url, body); a transport error is a PullError."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.geturl(), r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, url, ""
    except (urllib.error.URLError, TimeoutError) as e:
        raise PullError(f"fetch failed: {e}", "SOURCE_BLOCKED")


def fetch(url: str, direct=None, relay=None) -> str:
    """Direct GET; on a bot-wall status, one retry through the relay."""
    status, final, body = (direct or _direct)(url)
    if status in BLOCK_STATUSES:
        got = (relay or fetch_via_relay)(url)
        if got is None:
            raise PullError(f"HTTP {status} from {url} (relay not configured or unreachable)", "SOURCE_BLOCKED")
        relay_status, body = got
        if relay_status != 200:
            raise PullError(f"HTTP {status} from {url}, relay HTTP {relay_status}", "SOURCE_BLOCKED")
        final = url
    elif status != 200:
        raise PullError(f"HTTP {status} from {url}", "SOURCE_BLOCKED")
    if re.search(r"/(login|sign-?in|subscribe)\b", final):
        raise PullError(f"redirected to a login/paywall page: {final}", "SOURCE_BLOCKED")
    return body


def parse_page_meta(html: str, today: date, segment: int = SEGMENT, label: str = ROS_LABEL) -> dict:
    """Vintage date plus a check that the page is still the asked period / All Offense."""
    if not re.search(r'<option value="?%d"?[^>]*\bselected\b[^>]*>\s*%s\s*<' % (segment, label), html):
        raise PullError(f"Period {segment} is no longer the selected {label!r} option")
    if not re.search(r'<option value="?%d"?[^>]*\bselected\b[^>]*>\s*All Offense' % POSITION, html):
        raise PullError(f"Position {POSITION} is no longer the selected 'All Offense' option")
    m = re.search(r"last updated\s+(\d{1,2})-(\d{1,2})", html, re.I)
    if not m:
        raise PullError("no 'Last updated MM-DD' stamp on the page")
    month, day = int(m.group(1)), int(m.group(2))
    try:
        vintage = date(today.year, month, day)
        if vintage > today + timedelta(days=1):  # stamp from last December, read in January
            vintage = date(today.year - 1, month, day)
    except ValueError:
        raise PullError(f"unreadable 'Last updated' stamp {m.group(0)!r}")
    return {"vintage_date": vintage}


def week_segment(html: str, week: int) -> int:
    """The Period option labelled 'Week <week>' on the page's own list."""
    found = {int(w): int(seg) for seg, w in WEEK_OPTION_RE.findall(html)}
    if not found:
        labels = re.findall(r'<option value="?(\d+)"?[^>]*>\s*([^<]{1,40}?)\s*</option>', html)[:12]
        raise PullError(f"no 'Week N' options in the Period list (options seen: {labels})")
    if week not in found:
        raise PullError(f"no 'Week {week}' option in the Period list (have {sorted(found)})")
    return found[week]


def week_label(week: int) -> str:
    return r"(?:\d{4}\s+)?(?:NFL\s+)?Week\s+%d" % week


def parse_csv(body: str, label: str) -> list[dict]:
    if not body.lstrip().startswith("Rank,"):
        raise PullError(f"{label}: body is not the projections CSV", "SOURCE_BLOCKED")
    reader = csv.DictReader(io.StringIO(body))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise PullError(f"{label}: required columns gone: {missing}")
    return list(reader)


def _pts(raw: str, label: str, name: str, pts_range: tuple[float, float] = PTS_RANGE):
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise PullError(f"{label}: {name} Pts={raw!r} is not a number", "VALUE_RANGE")
    if not (pts_range[0] <= v <= pts_range[1]):
        raise PullError(f"{label}: {name} Pts={v} outside {pts_range}", "VALUE_RANGE")
    return v if v else None


def display_name(raw: str) -> str:
    last, sep, first = raw.partition(",")
    return f"{first.strip()} {last.strip()}".strip() if sep else raw.strip()


def build_snapshot(tables: dict[str, list[dict]], meta: dict, now: datetime | None = None,
                   max_age_days: int = MAX_AGE_DAYS, week: int | None = None) -> dict:
    """Rest-of-year snapshot, or with `week` the held weekly snapshot (own schema,
    floors and range; never mixed with rest-of-year)."""
    weekly = week is not None
    floors = WEEKLY_ROW_FLOORS if weekly else ROW_FLOORS
    pts_range = WEEKLY_PTS_RANGE if weekly else PTS_RANGE
    now = now or datetime.now(timezone.utc)
    age = (now.date() - meta["vintage_date"]).days
    if age > max_age_days:
        raise PullError(f"'Last updated' is {age} days old (max {max_age_days})", "SOURCE_STALE")
    by_id: dict[str, dict] = {}
    dropped = {"non_skill_position": 0, "unprojected": 0}
    for scoring, rows in tables.items():
        for r in rows:
            pos = r["Position"]
            if pos not in POSITIONS:
                dropped["non_skill_position"] += 1
                continue
            pid, name = r["Player ID"], display_name(r["Player Name"])
            rec = by_id.setdefault(pid, {
                "player_name": name, "player_norm": norm_plain(name), "pos": pos,
                "team": r["Team"] or None, "fantasysharks_id": int(pid),
                "pts": {s: None for s in SCORINGS}})
            rec["pts"][scoring] = _pts(r["Pts"], scoring, name, pts_range)
    rows = []
    for rec in by_id.values():
        p = rec["pts"]
        if all(v is None for v in p.values()):
            dropped["unprojected"] += 1
            continue
        if None not in p.values() and not (p["non_ppr"] <= p["half_ppr"] <= p["ppr"]):
            raise PullError(f"{rec['player_name']} scoring sets out of order: {p}", "VALUE_RANGE")
        rows.append(rec)
    rows.sort(key=lambda r: r["fantasysharks_id"])
    for pos in POSITIONS:
        n = sum(1 for r in rows if r["pos"] == pos and r["pts"]["half_ppr"])
        if n < floors[pos]:
            raise PullError(f"{pos} has {n} half-PPR rows (floor {floors[pos]})", "SOURCE_TRUNCATED")
    pairs = [(r["fantasysharks_id"], r["pts"]["half_ppr"]) for r in rows if r["pts"]["half_ppr"] is not None]
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    snap = {
        "schema": WEEKLY_SCHEMA if weekly else SCHEMA,
        "source": WEEKLY_SOURCE if weekly else "fantasysharks", "source_url": BASE,
        "segment": meta.get("segment", SEGMENT),
        "fetched_at": now.isoformat(timespec="seconds"),
        "vintage_date": meta["vintage_date"].isoformat(), "fingerprint": fingerprint,
        "rows": rows, "row_count": len(rows), "dropped": dropped,
    }
    if weekly:
        snap["week"] = week
    return snap


def pull(delay: float, max_age_days: int, fetcher=None) -> dict:
    get = fetcher or fetch
    now = datetime.now(timezone.utc)
    meta = parse_page_meta(get(url_for(SCORINGS["half_ppr"], False)), now.date())
    tables = {}
    for scoring, sid in SCORINGS.items():
        time.sleep(delay)
        tables[scoring] = parse_csv(get(url_for(sid, True)), scoring)
    return build_snapshot(tables, meta, now, max_age_days)


def pull_weekly(delay: float, max_age_days: int, week: int | None = None, fetcher=None) -> dict:
    """The current content week's projections, its Segment read off the page."""
    get = fetcher or fetch
    now = datetime.now(timezone.utc)
    week = week or content_week(now.date())
    segment = week_segment(get(url_for(SCORINGS["half_ppr"], False)), week)
    time.sleep(delay)
    meta = parse_page_meta(get(url_for(SCORINGS["half_ppr"], False, segment)), now.date(),
                           segment, week_label(week))
    meta["segment"] = segment
    tables = {}
    for scoring, sid in SCORINGS.items():
        time.sleep(delay)
        tables[scoring] = parse_csv(get(url_for(sid, True, segment)), scoring)
    return build_snapshot(tables, meta, now, max_age_days, week=week)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--period", choices=("ros", "weekly"), default="ros",
                    help="ros (default, saved) or weekly (held: separate snapshot, never blended)")
    ap.add_argument("--week", type=int, help="weekly only: content week (default: the current one)")
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between requests")
    ap.add_argument("--max-age-days", type=int)
    ap.add_argument("--replay-dir", help="read page.html, non_ppr.csv, half_ppr.csv, ppr.csv from here instead of fetching")
    a = ap.parse_args(argv)
    weekly = a.period == "weekly"
    max_age = a.max_age_days if a.max_age_days is not None else (WEEKLY_MAX_AGE_DAYS if weekly else MAX_AGE_DAYS)
    try:
        if a.replay_dir:
            d = Path(a.replay_dir)
            html = (d / "page.html").read_text(encoding="utf-8")
            today = datetime.now(timezone.utc).date()
            week = (a.week or content_week(today)) if weekly else None
            if weekly:
                segment = week_segment(html, week)
                meta = parse_page_meta(html, today, segment, week_label(week))
                meta["segment"] = segment
            else:
                meta = parse_page_meta(html, today)
            tables = {s: parse_csv((d / f"{s}.csv").read_text(encoding="utf-8"), s) for s in SCORINGS}
            snap = build_snapshot(tables, meta, max_age_days=max_age, week=week)
        elif weekly:
            snap = pull_weekly(a.delay, max_age, a.week)
        else:
            snap = pull(a.delay, max_age)
    except PullError as e:
        print(f"FANTASYSHARKS PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    where = f", week {snap['week']} (Segment {snap['segment']})" if "week" in snap else ""
    print(f"{snap['source']}: {snap['row_count']} rows{where}, fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
