#!/usr/bin/env python3
"""Scrape Razzball rest-of-season fantasy projections -> razzball snapshot.json.

Repo-owned replacement for Muse's `razzball-projections-pull` (disabled
2026-10-06, ops-ownership-001). JEG-18/GAP-030 named `pull_razzball_ros.py` as
the puller but it never landed in the repo; the row shape here is the one
already stored in public.razzball_projections (raw_stats keys verified against
the 2026-10-01 vintage: pg_* = season total / games, share_* = Razzball's
"% Tm" columns verbatim, rz_*_ppg = Razzball's published PPG columns).

Pages (one per position, first `neorazzstatstable` table on each):
  https://football.razzball.com/projections-{qb,rb,wr,te}-restofseason/

Output: <out-dir>/snapshot.json, the shape save_razzball_references.py reads:
  {"schema", "source", "vintage_date", "source_urls", "fetched_at",
   "rows": [{player_name, player_norm, pos, team, health, games_reported,
             pg_*..., share_rush, share_tgt, rz_std_ppg, rz_half_ppr_ppg,
             rz_ppr_ppg, razzball_snapshot_date}],
   "review_rows": [...], "row_count", "review_count", "summary"}

Reconciled with Muse's real script (JEG-433, 2026-10-07; the script itself was
VM-local and never in a repo). Carried over from it: the browser-like Accept
header (a bare request returns an empty HTTP 200), the stats-table rule (the
table that carries BOTH a Name column and the published "STD PPG" column; on
2026-09-21 Razzball added a larger overall PTS/G table that must never win on
row count), per-game = published total / Games (Razzball published Games and
counting totals doubled in September, the ratio cancels it, and the published
PPG columns are the canonical legs), and the PPG-consistency gate (component
implied standard PPG must match the published STD PPG). Row floors are ours
(Muse's only floor was 50 rows per position); they sit below the 2026-10-06
vintage (QB 102, RB 163, WR 260, TE 147).

Fail closed (exit 1, no snapshot written) with a NAMED error code on stderr,
`RAZZBALL PULL FAILED [<CODE>]: ...`:
  SOURCE_BLOCKED       HTTP 401/402/403/429/451, a transport failure, an empty
                       body, or a short page with no stats table (bot wall)
  SOURCE_HTTP_ERROR    any other non-200
  SCHEMA_CHANGED       no Name + STD PPG table, or a required column missing
  TRUNCATED            a position below its row floor, or total below floor
  PPG_INCONSISTENT     component-implied PPG disagrees with published PPG
Unparseable rows go to review_rows, never zero-filled. Identity (player_key)
is resolved later by the saver against public.players, never here.

Dating: vintage_date is the pull date (Central), i.e. the day this page was
read; the page's own "updated" stamp, when present, is recorded verbatim in
page_stamps and printed, never rewritten into the vintage.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from canonical_players import norm_plain  # noqa: E402  (the stored player_norm convention)

URL = "https://football.razzball.com/projections-{pos}-restofseason/"
POSITIONS = ("QB", "RB", "WR", "TE")
ROW_FLOORS = {"QB": 60, "RB": 100, "WR": 150, "TE": 80}
TOTAL_FLOOR = 400
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Snapshot per-game stat key -> the page header that carries its season total.
# One entry per header spelling seen on the four pages (2026-10-06).
TOTAL_HEADERS = {
    "pg_snaps": ("Snaps", "Snap"),
    "pg_cmp": ("Cmp",),
    "pg_att": ("Att",),
    "pg_pass_yds": ("Pass Yds",),
    "pg_pass_td": ("Pass TD",),
    "pg_int": ("Int",),
    "pg_sacks": ("Scks",),
    "pg_rush_att": ("Rush",),
    "pg_rush_yds": ("Rush Yds",),
    "pg_rush_td": ("Run TD",),
    "pg_fum": ("Fum Lst", "Fum Lost"),
    "pg_tgt": ("Tgt",),
    "pg_rec": ("Rec",),
    "pg_rec_yds": ("Rec Yds",),
    "pg_rec_td": ("Rec TD",),
}
SHARE_HEADERS = {"share_rush": ("% Tm Rush",), "share_tgt": ("% Tm Tgt",)}
GAMES_HEADERS = ("Games", "G")
HEALTH_HEADERS = ("Health", "H")
PPG_HEADERS = {
    "rz_std_ppg": ("STD PPG",),
    "rz_half_ppr_ppg": ("1/2 PPR PPG",),
    "rz_ppr_ppg": ("PPR PPG",),
}
# Columns every page must carry for its rows to be priced at all.
REQUIRED = {
    "QB": ("Name", "Team", "Games", "STD PPG", "Att", "Pass Yds"),
    "RB": ("Name", "Team", "G", "STD PPG", "1/2 PPR PPG", "PPR PPG", "Rush"),
    "WR": ("Name", "Team", "G", "STD PPG", "1/2 PPR PPG", "PPR PPG", "Tgt"),
    "TE": ("Name", "Team", "G", "STD PPG", "1/2 PPR PPG", "PPR PPG", "Tgt"),
}


BLOCK_STATUSES = {401, 402, 403, 429, 451}
SHORT_PAGE_BYTES = 50000  # Muse's bot-wall heuristic: a real page is far larger
PPG_TOLERANCE = 0.5
STAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [AP]M \w+)")
ACCEPT = ("text/html,application/xhtml+xml,application/xml;q=0.9,"
          "image/avif,image/webp,*/*;q=0.8")


class PullError(RuntimeError):
    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code = code


def fetch(url: str, timeout: int = 60) -> tuple[int | None, str]:
    """curl with a browser UA (same transport as ops/watchdog/_common.fetch)."""
    try:
        p = subprocess.run(
            ["curl", "-sS", "-L", "-o", "-", "-w", "\n%{http_code}", "-A", UA,
             "--max-time", str(timeout),
             "-H", f"Accept: {ACCEPT}",
             "-H", "Accept-Language: en-US,en;q=0.9", url],
            capture_output=True, text=True, timeout=timeout + 15)
    except Exception as e:  # pragma: no cover - transport failure
        return None, f"curl exception: {e}"
    body, _, code = p.stdout.rpartition("\n")
    try:
        return int(code.strip()), body
    except ValueError:
        return None, p.stderr or "curl output unparseable"


def _cell_text(raw: str) -> str:
    return htmllib.unescape(re.sub(r"<[^>]+>", "", raw)).strip()


def parse_tables(page: str) -> list[tuple[list[str], list[list[str]]]]:
    """Every <table> on the page as (headers, data rows)."""
    out = []
    for body in re.findall(r"<table[^>]*>(.*?)</table>", page, re.S):
        headers = [_cell_text(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            cells = [_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if cells:
                rows.append(cells)
        out.append((headers, rows))
    return out


def parse_table(page: str, required_col: str = "STD PPG") -> tuple[list[str], list[list[str]]]:
    """The projections table: the largest table with a Name column AND the
    published PPG column (Muse's pick_table rule). Never the largest by row
    count alone: the overall PTS/G table and the sidebar have Name but no PPG
    legs."""
    best = None
    for headers, rows in parse_tables(page):
        if "Name" in headers and required_col in headers and (
                best is None or len(rows) > len(best[1])):
            best = (headers, rows)
    if best is None:
        if len(page) < SHORT_PAGE_BYTES:
            raise PullError("SOURCE_BLOCKED",
                            f"no stats table and the page is only {len(page)} bytes "
                            "(bot wall or empty body)")
        raise PullError("SCHEMA_CHANGED",
                        f"no table with a Name column and {required_col} found")
    return best


def _num(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        v = float(raw.replace(",", ""))
    except ValueError:
        return None
    return v if v == v else None


def _col(headers: list[str], names: tuple[str, ...]) -> int | None:
    for n in names:
        if n in headers:
            return headers.index(n)
    return None


def build_rows(pos: str, headers: list[str], rows: list[list[str]], vintage: str
               ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    missing = [h for h in REQUIRED[pos] if h not in headers]
    if missing:
        raise PullError("SCHEMA_CHANGED", f"{pos}: page layout changed, missing columns {missing} (have {headers})")
    i_name, i_team = headers.index("Name"), headers.index("Team")
    i_games, i_health = _col(headers, GAMES_HEADERS), _col(headers, HEALTH_HEADERS)
    clean: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for cells in rows:
        if len(cells) != len(headers):
            review.append({"reason": "cell_count_mismatch", "pos": pos, "cells": cells[:4]})
            continue
        name = cells[i_name]
        games = _num(cells[i_games])
        if not name or not games or games <= 0:
            review.append({"reason": "missing_name_or_games", "pos": pos, "player_name": name,
                           "games_raw": cells[i_games]})
            continue
        ppg: dict[str, float | None] = {}
        for key, names in PPG_HEADERS.items():
            i = _col(headers, names)
            ppg[key] = _num(cells[i]) if i is not None else None
        if pos == "QB":
            # The QB page publishes STD PPG only: a QB has no reception points,
            # so all three scorings are the same number (matches every stored
            # QB row: per_game_standard == half == ppr).
            ppg["rz_half_ppr_ppg"] = ppg["rz_ppr_ppg"] = ppg["rz_std_ppg"]
        if any(v is None for v in ppg.values()):
            review.append({"reason": "missing_or_non_numeric_ppg", "pos": pos,
                           "player_name": name})
            continue
        row: dict[str, Any] = {
            "player_name": name,
            "player_norm": norm_plain(name),
            "pos": pos,
            "team": cells[i_team],
            "health": cells[i_health] if i_health is not None else "",
            "games_reported": games,
        }
        bad = False
        for key, names in TOTAL_HEADERS.items():
            i = _col(headers, names)
            if i is None:
                row[key] = 0  # stat not published for this position (stored rows carry 0)
                continue
            total = _num(cells[i])
            if total is None:
                bad = True
                break
            row[key] = round(total / games, 4)
        if bad:
            review.append({"reason": "non_numeric_stat", "pos": pos, "player_name": name})
            continue
        for key, names in SHARE_HEADERS.items():
            i = _col(headers, names)
            row[key] = (_num(cells[i]) or 0) if i is not None else 0
        row.update(ppg)
        row["razzball_snapshot_date"] = vintage
        clean.append(row)
    return clean, review


def implied_std_pg(row: dict[str, Any]) -> float:
    """Component-implied standard PPG under Razzball's scoring (1/25 pass yds,
    4 pass TD, -2 INT, 1/10 rush and rec yds, 6 per rush/rec TD, -2 fum lost).
    Validates the parse: a wrong column mapping shows up as a large gap."""
    return (row["pg_pass_yds"] / 25.0 + 4 * row["pg_pass_td"] - 2 * row["pg_int"]
            + row["pg_rush_yds"] / 10.0 + 6 * row["pg_rush_td"]
            + row["pg_rec_yds"] / 10.0 + 6 * row["pg_rec_td"] - 2 * row["pg_fum"])


def ppg_gate(rows: list[dict[str, Any]]) -> list[str]:
    """Raise PPG_INCONSISTENT when too many rows disagree; else return the
    names of the few tolerated outliers (Muse: more than max(5, 5%) fails)."""
    bad = [r for r in rows if abs(implied_std_pg(r) - r["rz_std_ppg"]) > PPG_TOLERANCE]
    if len(bad) > max(5, int(0.05 * len(rows))):
        raise PullError("PPG_INCONSISTENT",
                        f"{len(bad)}/{len(rows)} rows differ from published STD PPG by more "
                        f"than {PPG_TOLERANCE} (e.g. {bad[0]['player_name']})")
    return [b["player_name"] for b in bad]


def pull(vintage: str, fetch_fn: Callable[[str], tuple[int | None, str]] = fetch
         ) -> dict[str, Any]:
    all_rows: list[dict[str, Any]] = []
    all_review: list[dict[str, Any]] = []
    by_pos: dict[str, int] = {}
    urls = {}
    stamps: dict[str, str] = {}
    for pos in POSITIONS:
        url = URL.format(pos=pos.lower())
        urls[pos] = url
        status, page = fetch_fn(url)
        if status in BLOCK_STATUSES or status is None:
            raise PullError("SOURCE_BLOCKED", f"{pos}: status={status!r} url={url} ({page[:120]!r})")
        if status != 200:
            raise PullError("SOURCE_HTTP_ERROR", f"{pos}: status={status!r} url={url}")
        if not page.strip():
            raise PullError("SOURCE_BLOCKED", f"{pos}: HTTP 200 with an empty body url={url}")
        m = STAMP_RE.search(page)
        stamps[pos] = m.group(1) if m else "unknown"
        headers, rows = parse_table(page)
        clean, review = build_rows(pos, headers, rows, vintage)
        if len(clean) < ROW_FLOORS[pos]:
            raise PullError("TRUNCATED", f"{pos}: only {len(clean)} clean rows (floor {ROW_FLOORS[pos]}); "
                            "refusing a truncated pull")
        by_pos[pos] = len(clean)
        all_rows += clean
        all_review += review
    if len(all_rows) < TOTAL_FLOOR:
        raise PullError("TRUNCATED", f"only {len(all_rows)} rows in total (floor {TOTAL_FLOOR})")
    ppg_outliers = ppg_gate(all_rows)
    return {
        "schema": "trade-value-razzball-snapshot-v1",
        "source": "razzball",
        "vintage_date": vintage,
        "source_urls": urls,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": all_rows,
        "review_rows": all_review,
        "row_count": len(all_rows),
        "review_count": len(all_review),
        "summary": {"n_rows": len(all_rows), "n_review": len(all_review), "by_pos": by_pos,
                    "ppg_outliers": ppg_outliers},
        "page_stamps": stamps,
        "scoring_note": ("rz_*_ppg are Razzball's published per-game columns (canonical); "
                         "pg_* are season totals divided by Razzball's Games column."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", required=True, help="vintage date (YYYY-MM-DD), normally today CT")
    ap.add_argument("--out-dir", required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        snap = pull(args.date)
    except PullError as e:
        print(f"RAZZBALL PULL FAILED [{e.code}]: {e}", file=sys.stderr, flush=True)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "snapshot.json"
    out.write_text(json.dumps(snap, indent=1, sort_keys=True))
    print(f"razzball {args.date}: {snap['row_count']} rows {snap['summary']['by_pos']}, "
          f"{snap['review_count']} review, page stamps {snap['page_stamps']} -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
