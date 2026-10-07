#!/usr/bin/env python3
"""Scrape Razzball rest-of-season fantasy projections -> razzball snapshot.json.

Repo-owned replacement for Muse's `razzball-projections-pull` (disabled
2026-10-06, ops-ownership-001). JEG-18/GAP-030 named `pull_razzball_ros.py` as
the puller but it never landed in the repo; the row shape here is the one
already stored in public.razzball_projections (raw_stats keys verified against
the 2026-10-01 vintage: pg_* = season total / games, share_* = Razzball's
"% Tm" columns verbatim, rz_*_ppg = Razzball's published PPG columns).

Pages (one per position; Muse's exact URLs, no trailing slash):
  https://football.razzball.com/projections-{qb,rb,wr,te}-restofseason
Table choice (Muse's rule, learned 2026-09-21): the projections table is the
largest <table> whose header has BOTH `Name` and `STD PPG`. Razzball appends an
overall `#/Name/Team/Pos/PTS/G` table (and the sidebar reuses the same table
id) that is bigger than the QB table but carries no PPG legs; position in the
page and row count alone never decide.

Output: <out-dir>/snapshot.json, the shape save_razzball_references.py reads:
  {"schema", "source", "vintage_date", "source_urls", "fetched_at",
   "rows": [{player_name, player_norm, pos, team, health, games_reported,
             pg_*..., share_rush, share_tgt, rz_std_ppg, rz_half_ppr_ppg,
             rz_ppr_ppg, razzball_snapshot_date}],
   "review_rows": [...], "row_count", "review_count", "summary"}

Fail closed (non-zero exit, no snapshot written), each with a named code on
the `RAZZBALL PULL FAILED [CODE]` line the workflow turns into the monitored
error_code:
  SOURCE_BLOCKED   non-200 / bot wall / empty or tiny body (HTTP 402, 403, 429...)
  SOURCE_LAYOUT    no stats table, a required column gone, no page stamp
  SOURCE_TRUNCATED a position below its row floor, or < 400 rows in total
  PPG_GATE         component-implied standard PPG disagrees with the published
                   PPG column on too many rows (columns shifted / scoring changed)
Unparseable rows go to review_rows, never zero-filled. Identity (player_key) is
resolved later by the saver against public.players, never here.

DATING: the vintage is the date in Razzball's own "Updated: YYYY-MM-DD ..."
stamp (the OLDEST of the four pages), not the run date. A daily run against an
unchanged page therefore re-saves the same vintage (idempotent upsert) instead
of minting a fresh-looking one, so the import-health age (GAP-024) measures the
content, not the cron. `fetched_at` and every page stamp are kept in the
snapshot. `--date` overrides (tests only).

Also emits <out-dir>/razzball_projections.csv in Muse's exact column schema
(data/inputs/razzball_projections.csv, the pipelines/bake_players.py input).
Muse's doubling quirk (Games and totals published 2x) cancels in total/games, so
per-game stats are right whether or not the page doubles them.
"""
from __future__ import annotations

import argparse
import csv
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
from player_resolver import legacy_label  # noqa: E402  (JEG-438: the stored player_norm convention)

URL = "https://football.razzball.com/projections-{pos}-restofseason"
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
    def __init__(self, msg: str, code: str = "SOURCE_LAYOUT"):
        super().__init__(msg)
        self.code = code


STAMP_RE = re.compile(r"Updated:?\s*(\d{4}-\d{2}-\d{2})\s+\d{1,2}:\d{2}:\d{2}\s*[AP]M\s*\w*", re.I)
MIN_BODY = 20000  # Muse used 50 kB on the largest page; the TE page is smaller
PPG_TOLERANCE = 0.5       # Muse's consistency gate
PPG_MAX_BAD = (5, 0.05)   # more than max(5, 5% of rows) diverging fails closed


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
    """Headers and data rows of the projections table: the largest <table> whose
    header carries both `Name` and `STD PPG` (see the module docstring)."""
    best: tuple[list[str], list[list[str]]] | None = None
    for m in re.finditer(r"<table[^>]*>(.*?)</table>", page, re.S):
        body = m.group(1)
        headers = [_cell_text(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", body, re.S)]
        if "Name" not in headers or "STD PPG" not in headers:
            continue
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
            cells = [_cell_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if cells:
                rows.append(cells)
        if best is None or len(rows) > len(best[1]):
            best = (headers, rows)
    if best is None:
        raise PullError("no table with both a Name and a STD PPG column found "
                        "(page layout changed?)", "SOURCE_LAYOUT")
    return best


def page_stamp(page: str) -> str | None:
    """ISO date of Razzball's own 'Updated: YYYY-MM-DD hh:mm:ss PM EST' stamp."""
    m = STAMP_RE.search(re.sub(r"<[^>]+>", " ", page))
    return m.group(1) if m else None


def implied_std_pg(row: dict[str, Any]) -> float:
    """Component-implied standard-scoring PPG (Muse's schema gate): validates the
    parse and Razzball's scoring against the published STD PPG column."""
    return (row["pg_pass_yds"] / 25.0 + 4 * row["pg_pass_td"] - 2 * row["pg_int"]
            + row["pg_rush_yds"] / 10.0 + 6 * row["pg_rush_td"]
            + row["pg_rec_yds"] / 10.0 + 6 * row["pg_rec_td"] - 2 * row["pg_fum"])


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
            "player_norm": legacy_label(name, "plain"),
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


def pull(vintage: str | None, fetch_fn: Callable[[str], tuple[int | None, str]] = fetch
         ) -> dict[str, Any]:
    pages: dict[str, tuple[list[str], list[list[str]]]] = {}
    stamps: dict[str, str] = {}
    urls = {}
    for pos in POSITIONS:
        url = URL.format(pos=pos.lower())
        urls[pos] = url
        status, page = fetch_fn(url)
        if status != 200:
            raise PullError(f"{pos}: fetch failed status={status!r} url={url} "
                            "(bot wall or outage)", "SOURCE_BLOCKED")
        if len(page) < MIN_BODY or "<table" not in page:
            raise PullError(f"{pos}: page body too small/empty ({len(page)} bytes) -- "
                            "likely bot-walled", "SOURCE_BLOCKED")
        pages[pos] = parse_table(page)
        stamp = page_stamp(page)
        if not stamp:
            raise PullError(f"{pos}: no 'Updated: <date>' stamp on the page; refusing to "
                            "date the data by the run date", "SOURCE_LAYOUT")
        stamps[pos] = stamp
    if vintage is None:
        vintage = min(stamps.values())  # the oldest page bounds how fresh the pull is
    all_rows: list[dict[str, Any]] = []
    all_review: list[dict[str, Any]] = []
    by_pos: dict[str, int] = {}
    for pos in POSITIONS:
        headers, rows = pages[pos]
        clean, review = build_rows(pos, headers, rows, vintage)
        if len(clean) < ROW_FLOORS[pos]:
            raise PullError(f"{pos}: only {len(clean)} clean rows (floor {ROW_FLOORS[pos]}); "
                            "refusing a truncated pull", "SOURCE_TRUNCATED")
        by_pos[pos] = len(clean)
        all_rows += clean
        all_review += review
    if len(all_rows) < TOTAL_FLOOR:
        raise PullError(f"only {len(all_rows)} rows in total (floor {TOTAL_FLOOR})",
                        "SOURCE_TRUNCATED")
    bad = [r for r in all_rows if abs(implied_std_pg(r) - r["rz_std_ppg"]) > PPG_TOLERANCE]
    if len(bad) > max(PPG_MAX_BAD[0], int(PPG_MAX_BAD[1] * len(all_rows))):
        raise PullError(f"PPG consistency gate: {len(bad)}/{len(all_rows)} rows diverge "
                        f">{PPG_TOLERANCE} ppg from the published STD PPG "
                        f"(e.g. {bad[0]['player_name']})", "PPG_GATE")
    return {
        "schema": "trade-value-razzball-snapshot-v1",
        "source": "razzball",
        "vintage_date": vintage,
        "page_stamps": stamps,
        "source_urls": urls,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": all_rows,
        "review_rows": all_review,
        "row_count": len(all_rows),
        "review_count": len(all_review),
        "ppg_gate_diverging": [r["player_name"] for r in bad],
        "summary": {"n_rows": len(all_rows), "n_review": len(all_review), "by_pos": by_pos},
        "scoring_note": ("rz_*_ppg are Razzball's published per-game columns (canonical); "
                         "pg_* are season totals divided by Razzball's Games column."),
    }


CSV_COLUMNS = (["player", "player_norm", "pos", "team", "health", "games_reported"]
               + list(TOTAL_HEADERS) + list(SHARE_HEADERS) + list(PPG_HEADERS)
               + ["razzball_snapshot_date"])


def write_csv(snap: dict[str, Any], path: Path) -> None:
    """Muse's files/razzball_projections.csv schema (the bake_players.py input)."""
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for r in snap["rows"]:
            w.writerow([r["player_name"] if c == "player" else r[c] for c in CSV_COLUMNS])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", default=None,
                    help="override the vintage date (tests); default is Razzball's own page stamp")
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
    write_csv(snap, args.out_dir / "razzball_projections.csv")
    print(f"razzball vintage {snap['vintage_date']} (page stamps {snap['page_stamps']}): "
          f"{snap['row_count']} rows {snap['summary']['by_pos']}, "
          f"{snap['review_count']} review, {len(snap['ppg_gate_diverging'])} off the PPG gate "
          f"-> {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
