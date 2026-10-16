#!/usr/bin/env python3
"""JEG-671: pull the RotoBaller weekly trade value chart -> snapshot.json.

Source (public, no login, no paywall; measured 2026-10-16, HTTP 200, about 0.9 MB):
  stable URL  https://www.rotoballer.com/fantasy-football-trade-value-chart
  It redirects to ONE weekly article and was still on the Week 1 article (Sept 13) in
  week 6, so it cannot be trusted to be current. The puller therefore finds the newest
  article for the season on the site search page
  (https://www.rotoballer.com/?s=fantasy+football+trade+value+chart), whose results
  carry links like `fantasy-football-trade-value-chart-week-5-trades-rankings-buys-sells-2026/1961768`
  (weeks 1-5 listed on 2026-10-16), and falls back to the stable URL if search shows none.
The article has a server-rendered table (Rank | Trade Value | Player | Pos): a 0-100
redraft-style trade value, 200 rows in Week 5 (400 in Week 1, which also had K and DST).
Only QB/RB/WR/TE rows are kept. Scoring format and league size are NOT stated in the
table or the article text (it links PPR, half-PPR and standard ranking pages
separately), so the snapshot carries `scoring: null`. That is a methods question for
the DDF lane; this puller does not guess.

Output: <out-dir>/snapshot.json
  {"schema", "source", "source_url", "article_week", "season", "published_at",
   "scoring", "fetched_at", "vintage_date", "fingerprint",
   "rows": [{player_name, player_norm, pos, rank, trade_value, rotoballer_id}],
   "row_count", "dropped": {...}}
Identity (player_key) is resolved later by a saver against public.players via
lib/canonical_players; this puller only normalizes the name.

DATING: the article title names the week ("Week 5 ... (2026)") and the page carries a
datePublished stamp; `vintage_date` is that publish date. `fingerprint` is sha256 of
sorted (name, value) pairs.

Fail closed (non-zero exit, no snapshot written), named on the
`ROTOBALLER PULL FAILED [CODE]` line:
  SOURCE_BLOCKED    curl failure, non-200, login redirect, or a tiny body
  SOURCE_LAYOUT     no title week, no Rank/Trade Value table, bad rows, a field is gone
  SOURCE_STALE      article week is behind the NFL week, or from another season
  SOURCE_TRUNCATED  a position below its row floor
  VALUE_RANGE       a trade value outside 0..100 (scale changed)
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "pipelines"))
from canonical_players import norm_plain  # noqa: E402
from nfl_week import current_nfl_week  # noqa: E402

STABLE_URL = "https://www.rotoballer.com/fantasy-football-trade-value-chart"
SEARCH_URL = "https://www.rotoballer.com/?s=fantasy+football+trade+value+chart"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MIN_BODY = 20_000
POSITIONS = ("QB", "RB", "WR", "TE")
# row floors, about 40% of the Week 5 counts (QB 28, RB 65, WR 77, TE 30)
ROW_FLOORS = {"QB": 11, "RB": 26, "WR": 31, "TE": 12}
VALUE_MIN, VALUE_MAX = 0, 100
SCHEMA = "rotoballer_trade_value_v1"
_ARTICLE = re.compile(
    r'https://www\.rotoballer\.com/fantasy-football-trade-value-chart-week-(\d+)-[a-z0-9-]*?-(\d{4})/(\d+)')
_TITLE = re.compile(r"<title>[^<]*?\bWeek\s+(\d+)\b[^<]*?\((\d{4})\)[^<]*</title>", re.S)
_PUBLISHED = re.compile(r'"datePublished":"(\d{4}-\d{2}-\d{2})')
_ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
_CELL = re.compile(r"<td>(.*?)</td>", re.S)
_ID = re.compile(r'data-id="(\d+)"')


class PullError(RuntimeError):
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


def fetch(url: str) -> tuple[str, str]:
    """(body, final_url) through curl; raises SOURCE_BLOCKED on any failure."""
    cmd = ["curl", "-sS", "-L", "--tlsv1.2", "--max-time", "60", "-A", UA,
           "-w", "\n%{http_code} %{url_effective}", url]
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=90)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise PullError(f"curl failed: {e}", "SOURCE_BLOCKED")
    if res.returncode != 0:
        raise PullError(f"curl exit {res.returncode}: {res.stderr.decode(errors='replace')[:200]}", "SOURCE_BLOCKED")
    out = res.stdout.decode("utf-8", errors="replace")
    body, _, tail = out.rpartition("\n")
    status, _, final = tail.partition(" ")
    if status != "200":
        raise PullError(f"HTTP {status} from {url}", "SOURCE_BLOCKED")
    if re.search(r"/(login|sign-?in|subscribe)\b", final):
        raise PullError(f"redirected to a login/paywall page: {final}", "SOURCE_BLOCKED")
    return body, final


def newest_article_url(search_body: str, season: int) -> str | None:
    """Link of the highest-week trade value chart article for `season`, or None."""
    found = {}
    for m in _ARTICLE.finditer(search_body):
        week, year, _ = int(m.group(1)), int(m.group(2)), m.group(3)
        if year == season:
            found[week] = m.group(0)
    return found[max(found)] if found else None


def fetch_article(today: date) -> tuple[str, str]:
    try:
        search, _ = fetch(SEARCH_URL)
        url = newest_article_url(search, today.year)
    except PullError:
        url = None
    if url is None:
        url = STABLE_URL
    return fetch(url)


def parse_article(body: str) -> dict:
    """Title week/season, publish date and the raw table rows."""
    if len(body) < MIN_BODY:
        raise PullError(f"body is {len(body)} bytes (< {MIN_BODY})", "SOURCE_BLOCKED")
    t = _TITLE.search(body)
    if not t:
        raise PullError("title names no 'Week N ... (YYYY)'")
    published = _PUBLISHED.search(body)
    table = None
    for m in re.finditer(r"<table\b.*?</table>", body, re.S):
        head = re.sub(r"<[^>]+>", " ", m.group(0)[:1500])
        if re.search(r"\bRank\b", head) and re.search(r"Trade\s+Value", head) and re.search(r"\bPos\b", head):
            table = m.group(0)
            break
    if table is None:
        raise PullError("no Rank / Trade Value / Player / Pos table")
    return {"week": int(t.group(1)), "season": int(t.group(2)),
            "published": published.group(1) if published else None, "table": table}


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", cell))).strip()


def parse_rows(table: str) -> tuple[list[dict], dict]:
    rows, dropped = [], {"non_skill_position": 0}
    seen = set()
    for raw in _ROW.findall(table)[1:]:
        cells = _CELL.findall(raw)
        if len(cells) != 4:
            raise PullError(f"row has {len(cells)} cells, expected 4: {_text(raw)[:80]}")
        rank_s, value_s, name, pos = _text(cells[0]), _text(cells[1]), _text(cells[2]), _text(cells[3])
        if not (rank_s.isdigit() and re.fullmatch(r"\d+(\.\d+)?", value_s) and name and pos):
            raise PullError(f"unreadable row: {rank_s!r} {value_s!r} {name!r} {pos!r}")
        value = float(value_s)
        if not (VALUE_MIN <= value <= VALUE_MAX):
            raise PullError(f"{name} value {value} outside {VALUE_MIN}..{VALUE_MAX}", "VALUE_RANGE")
        if pos not in POSITIONS:
            dropped["non_skill_position"] += 1
            continue
        key = (norm_plain(name), pos)
        if key in seen:
            raise PullError(f"duplicate row for {name} {pos}")
        seen.add(key)
        ident = _ID.search(cells[2])
        rows.append({"player_name": name, "player_norm": key[0], "pos": pos, "rank": int(rank_s),
                     "trade_value": int(value) if value.is_integer() else value,
                     "rotoballer_id": int(ident.group(1)) if ident else None})
    return rows, dropped


def build_snapshot(body: str, url: str, today: date | None = None, now: datetime | None = None,
                   floors: dict | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = today or now.date()
    floors = ROW_FLOORS if floors is None else floors
    art = parse_article(body)
    nfl_week = current_nfl_week(today)
    if art["season"] != today.year:
        raise PullError(f"article is season {art['season']}, expected {today.year}", "SOURCE_STALE")
    if art["week"] < nfl_week:
        raise PullError(f"article is Week {art['week']}, NFL week is {nfl_week}", "SOURCE_STALE")
    rows, dropped = parse_rows(art["table"])
    for pos, floor in floors.items():
        n = sum(1 for r in rows if r["pos"] == pos)
        if n < floor:
            raise PullError(f"{pos} has {n} rows (floor {floor})", "SOURCE_TRUNCATED")
    pairs = sorted((r["player_norm"], r["trade_value"]) for r in rows)
    fingerprint = hashlib.sha256(json.dumps(pairs).encode()).hexdigest()[:16]
    return {"schema": SCHEMA, "source": "rotoballer", "source_url": url,
            "article_week": art["week"], "season": art["season"], "published_at": art["published"],
            "scoring": None, "fetched_at": now.isoformat(timespec="seconds"),
            "vintage_date": art["published"] or today.isoformat(), "fingerprint": fingerprint,
            "rows": rows, "row_count": len(rows), "dropped": dropped}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--html", help="parse this saved article instead of fetching (tests, replays)")
    ap.add_argument("--today", help="YYYY-MM-DD override for the NFL-week staleness check")
    a = ap.parse_args(argv)
    today = date.fromisoformat(a.today) if a.today else date.today()
    try:
        if a.html:
            body, url = Path(a.html).read_text(encoding="utf-8"), STABLE_URL
        else:
            body, url = fetch_article(today)
        snap = build_snapshot(body, url, today=today)
    except PullError as e:
        print(f"ROTOBALLER PULL FAILED [{e.code}] {e}", file=sys.stderr)
        return 1
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8")
    print(f"rotoballer: Week {snap['article_week']}, {snap['row_count']} rows, "
          f"fingerprint {snap['fingerprint']}, vintage {snap['vintage_date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
