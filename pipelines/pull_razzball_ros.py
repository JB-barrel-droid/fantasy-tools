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

Fail closed (non-zero exit, no snapshot written) on: a non-200 page, a missing
stats table, a header layout that lacks a required column, a position below
its row floor, or a total below 400 rows (Muse's own floor). Unparseable rows
go to review_rows, never zero-filled. Identity (player_key) is resolved later
by the saver against public.players, never here.
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


class PullError(RuntimeError):
    pass


def fetch(url: str, timeout: int = 60) -> tuple[int | None, str]:
    """curl with a browser UA (same transport as ops/watchdog/_common.fetch)."""
    try:
        p = subprocess.run(
            ["curl", "-sS", "-L", "-o", "-", "-w", "\n%{http_code}", "-A", UA,
             "--max-time", str(timeout),
             "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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


def parse_table(page: str) -> tuple[list[str], list[list[str]]]:
    """Headers and data rows of the FIRST neorazzstatstable on the page (the
    second is an unrelated sidebar list)."""
    m = re.search(r'<table[^>]*id="neorazzstatstable"[^>]*>(.*?)</table>', page, re.S)
    if not m:
        raise PullError("Razzball stats table (id=neorazzstatstable) not found")
    body = m.group(1)
    headers = [_cell_text(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if cells:
            rows.append(cells)
    return headers, rows


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
        raise PullError(f"{pos}: page layout changed, missing columns {missing} (have {headers})")
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


def pull(vintage: str, fetch_fn: Callable[[str], tuple[int | None, str]] = fetch
         ) -> dict[str, Any]:
    all_rows: list[dict[str, Any]] = []
    all_review: list[dict[str, Any]] = []
    by_pos: dict[str, int] = {}
    urls = {}
    for pos in POSITIONS:
        url = URL.format(pos=pos.lower())
        urls[pos] = url
        status, page = fetch_fn(url)
        if status != 200:
            raise PullError(f"{pos}: fetch failed status={status!r} url={url}")
        headers, rows = parse_table(page)
        clean, review = build_rows(pos, headers, rows, vintage)
        if len(clean) < ROW_FLOORS[pos]:
            raise PullError(f"{pos}: only {len(clean)} clean rows (floor {ROW_FLOORS[pos]}); "
                            "refusing a truncated pull")
        by_pos[pos] = len(clean)
        all_rows += clean
        all_review += review
    if len(all_rows) < TOTAL_FLOOR:
        raise PullError(f"only {len(all_rows)} rows in total (floor {TOTAL_FLOOR})")
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
        "summary": {"n_rows": len(all_rows), "n_review": len(all_review), "by_pos": by_pos},
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
        print(f"RAZZBALL PULL FAILED: {e}", file=sys.stderr, flush=True)
        return 1
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / "snapshot.json"
    out.write_text(json.dumps(snap, indent=1, sort_keys=True))
    print(f"razzball {args.date}: {snap['row_count']} rows {snap['summary']['by_pos']}, "
          f"{snap['review_count']} review -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
