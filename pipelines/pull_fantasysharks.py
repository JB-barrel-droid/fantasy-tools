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
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402

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


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def url_for(scoring_id: int, csv_out: bool) -> str:
    q = f"Segment={SEGMENT}&Position={POSITION}&scoring={scoring_id}"
    return f"{BASE}?csv=1&{q}" if csv_out else f"{BASE}?{q}"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            final = r.geturl()
            body = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise PullError(f"HTTP {e.code} from {url}", "SOURCE_BLOCKED")
    except (urllib.error.URLError, TimeoutError) as e:
        raise PullError(f"fetch failed: {e}", "SOURCE_BLOCKED")
    if re.search(r"/(login|sign-?in|subscribe)\b", final):
        raise PullError(f"redirected to a login/paywall page: {final}", "SOURCE_BLOCKED")
    return body


def parse_page_meta(html: str, today: date) -> dict:
    """Vintage date plus a check that the page is still rest-of-year / All Offense."""
    if not re.search(r'<option value="?%d"?[^>]*\bselected\b[^>]*>\s*\d{4} Rest of Year' % SEGMENT, html):
        raise PullError(f"Period {SEGMENT} is no longer the selected '<year> Rest of Year' option")
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


def parse_csv(body: str, label: str) -> list[dict]:
    if not body.lstrip().startswith("Rank,"):
        raise PullError(f"{label}: body is not the projections CSV", "SOURCE_BLOCKED")
    reader = csv.DictReader(io.StringIO(body))
    missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
    if missing:
        raise PullError(f"{label}: required columns gone: {missing}")
    return list(reader)


def _pts(raw: str, label: str, name: str):
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise PullError(f"{label}: {name} Pts={raw!r} is not a number", "VALUE_RANGE")
    if not (PTS_RANGE[0] <= v <= PTS_RANGE[1]):
        raise PullError(f"{label}: {name} Pts={v} outside {PTS_RANGE}", "VALUE_RANGE")
    return v if v else None


def display_name(raw: str) -> str:
    last, sep, first = raw.partition(",")
    return f"{first.strip()} {last.strip()}".strip() if sep else raw.strip()


def build_snapshot(tables: dict[str, list[dict]], meta: dict, now: datetime | None = None,
                   max_age_days: int = MAX_AGE_DAYS) -> dict:
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
            rec["pts"][scoring] = _pts(r["Pts"], scoring, name)
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
        if n < ROW_FLOORS[pos]:
            raise PullError(f"{pos} has {n} half-PPR rows (floor {ROW_FLOORS[pos]})", "SOURCE_TRUNCATED")
    pairs = [(r["fantasysharks_id"], r["pts"]["half_ppr"]) for r in rows if r["pts"]["half_ppr"] is not None]
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    return {
        "schema": SCHEMA, "source": "fantasysharks", "source_url": BASE, "segment": SEGMENT,
        "fetched_at": now.isoformat(timespec="seconds"),
        "vintage_date": meta["vintage_date"].isoformat(), "fingerprint": fingerprint,
        "rows": rows, "row_count": len(rows), "dropped": dropped,
    }


def pull(delay: float, max_age_days: int) -> dict:
    now = datetime.now(timezone.utc)
    meta = parse_page_meta(fetch(url_for(SCORINGS["half_ppr"], False)), now.date())
    tables = {}
    for scoring, sid in SCORINGS.items():
        time.sleep(delay)
        tables[scoring] = parse_csv(fetch(url_for(sid, True)), scoring)
    return build_snapshot(tables, meta, now, max_age_days)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--delay", type=float, default=5.0, help="seconds between requests")
    ap.add_argument("--max-age-days", type=int, default=MAX_AGE_DAYS)
    ap.add_argument("--replay-dir", help="read page.html, non_ppr.csv, half_ppr.csv, ppr.csv from here instead of fetching")
    a = ap.parse_args(argv)
    try:
        if a.replay_dir:
            d = Path(a.replay_dir)
            meta = parse_page_meta((d / "page.html").read_text(encoding="utf-8"), datetime.now(timezone.utc).date())
            tables = {s: parse_csv((d / f"{s}.csv").read_text(encoding="utf-8"), s) for s in SCORINGS}
            snap = build_snapshot(tables, meta, max_age_days=a.max_age_days)
        else:
            snap = pull(a.delay, a.max_age_days)
    except PullError as e:
        print(f"FANTASYSHARKS PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"fantasysharks: {snap['row_count']} rows, fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
