#!/usr/bin/env python3
"""Pull full-season NFL projections from Sleeper and normalize to the 7-category schema.

Source endpoint (unofficial but keyless; used by Sleeper's own app):
  https://api.sleeper.app/projections/nfl/2026
       ?season_type=regular
       &position[]=QB&position[]=RB&position[]=WR&position[]=TE
       &order_by=pts_ppr

Returns ~3,100 rows from a single company ("rotowire" at verification time
2026-10-05). Each row has a `stats` object with position-specific keys; this
script maps them to the canonical 7 categories:
  passing_yards   <- pass_yd
  passing_tds     <- pass_td
  rushing_yards   <- rush_yd
  rushing_tds     <- rush_td
  receiving_yards <- rec_yd
  receiving_tds   <- rec_td
  receptions      <- rec

Missing keys are written as empty cells (NULL). NULL means "Sleeper did not
project this stat for this player" -- distinct from 0, which would mean
"Sleeper projected this player to score zero". The view's COALESCE priority
(Vegas-first, FP-fills-elsewhere) depends on this distinction; coercing
NULL to 0 would silently widen the Vegas fill range and break the tension
flag.

Output: pipeline/data/sleeper_season_projections.csv

Fail-closed:
  - HTTP error or non-200 response aborts the pull and writes nothing.
  - Wrong company name logs a warning (not fatal) but does write.
  - Rows missing player_id or player.position are dropped (logged).
  - Same player_id appearing multiple times -> keep the latest last_modified.

Usage:
  python3 pipeline/bin/pull_sleeper_season_projections.py
"""
from __future__ import annotations

import csv
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# --- paths (script is at pipeline/bin/, pipeline/ is the project root) ---
SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
DATA_DIR = PIPELINE_DIR / "data"
OUT_CSV = DATA_DIR / "sleeper_season_projections.csv"

# --- endpoint + skill positions ---
ENDPOINT = "https://api.sleeper.app/projections/nfl/2026"
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
EXPECTED_COMPANY = "rotowire"   # log warning if it changes
HTTP_TIMEOUT = 30              # seconds
HTTP_RETRIES = 3
RETRY_BACKOFF = 2.0            # exponential backoff multiplier

# --- normalized CSV columns (contract) ---
CSV_COLS = [
    "sleeper_player_id",
    "player_name",
    "position",
    "team",
    "passing_yards",
    "passing_tds",
    "rushing_yards",
    "rushing_tds",
    "receiving_yards",
    "receiving_tds",
    "receptions",
    "snapshot_date",
    "company",
]

# Sleeper stat-key -> output-column mapping.
STAT_MAP = {
    "pass_yd": "passing_yards",
    "pass_td": "passing_tds",
    "rush_yd": "rushing_yards",
    "rush_td": "rushing_tds",
    "rec_yd":  "receiving_yards",
    "rec_td":  "receiving_tds",
    "rec":     "receptions",
}

log = logging.getLogger("pull_sleeper_season")


def normalize_sleeper_row(row: dict) -> Optional[dict]:
    """Map one Sleeper API row to the 7-category schema.

    Returns None if the row is unusable (missing player_id or position).
    Missing stats are kept as None -- they will be written as empty CSV cells
    (NULL in the downstream table). Never coerce missing stats to 0.
    """
    pid = row.get("player_id")
    player = row.get("player") or {}
    pos = player.get("position")
    if not pid or not pos:
        return None

    team = row.get("team") or player.get("team") or None
    first = (player.get("first_name") or "").strip()
    last = (player.get("last_name") or "").strip()
    full = f"{first} {last}".strip()

    stats = row.get("stats") or {}
    out = {col: None for col in CSV_COLS}
    out["sleeper_player_id"] = str(pid)
    out["player_name"] = full
    out["position"] = pos
    out["team"] = team
    out["company"] = row.get("company")

    for sleeper_k, csv_col in STAT_MAP.items():
        if sleeper_k in stats and stats[sleeper_k] is not None:
            try:
                out[csv_col] = float(stats[sleeper_k])
            except (TypeError, ValueError):
                out[csv_col] = None
        # else: stays None -> empty CSV cell -> SQL NULL. Do not coerce to 0.

    return out


def fetch_rows() -> list[dict]:
    """Hit the Sleeper endpoint, return the parsed JSON list.

    Raises RuntimeError on any HTTP failure (after retries). Never returns
    partial data on failure.
    """
    url = (
        f"{ENDPOINT}"
        "?season_type=regular"
        f"&position[]=QB&position[]=RB&position[]=WR&position[]=TE"
        f"&order_by=pts_ppr"
    )
    last_err = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            log.info("fetching %s (attempt %d/%d)", url, attempt, HTTP_RETRIES)
            req = urllib.request.Request(url, headers={"User-Agent": "wt-sleeper-vorp/1.0"})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status} from {url}")
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as e:
            last_err = e
            log.warning("attempt %d failed: %s", attempt, e)
            if attempt < HTTP_RETRIES:
                time.sleep(RETRY_BACKOFF ** attempt)
    raise RuntimeError(f"Sleeper endpoint unreachable after {HTTP_RETRIES} tries: {last_err}")


def dedupe(rows: list[dict]) -> list[dict]:
    """Dedupe by sleeper_player_id, keeping the row with the latest last_modified."""
    best = {}
    for r in rows:
        # last_modified is epoch ms (int) or null in the API
        lm = r.get("last_modified") or 0
        try:
            lm = int(lm)
        except (TypeError, ValueError):
            lm = 0
        prev = best.get(r["player_id"])
        if prev is None or lm > prev[1]:
            best[r["player_id"]] = (r, lm)
    return [t[0] for t in best.values()]


def write_csv(rows: list[dict], snapshot_date: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = OUT_CSV.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            r["snapshot_date"] = snapshot_date
            w.writerow({c: r.get(c) for c in CSV_COLS})
    tmp.replace(OUT_CSV)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    raw = fetch_rows()
    log.info("raw rows fetched: %d", len(raw))

    # Company sanity check
    companies = {r.get("company") for r in raw if r.get("company")}
    if EXPECTED_COMPANY not in companies:
        log.warning("expected company '%s' not present; got %s",
                    EXPECTED_COMPANY, sorted(companies))
    elif companies != {EXPECTED_COMPANY}:
        log.warning("unexpected companies present: %s", sorted(companies - {EXPECTED_COMPANY}))

    # Dedupe BEFORE filtering on position (so dedupe is exact on player_id)
    deduped = dedupe(raw)
    log.info("after dedupe (by player_id, latest last_modified): %d", len(deduped))

    # Normalize
    normalized = []
    skipped = 0
    for r in deduped:
        if (r.get("player") or {}).get("position") not in SKILL_POSITIONS:
            skipped += 1
            continue
        norm = normalize_sleeper_row(r)
        if norm is None:
            skipped += 1
            continue
        normalized.append(norm)
    log.info("normalized skill-position rows: %d (skipped %d non-skill / malformed)",
             len(normalized), skipped)

    # Spot-check log: top 5 by passing_yards / rushing_yards / receiving_yards
    for stat_col in ("passing_yards", "rushing_yards", "receiving_yards"):
        top = sorted(
            (r for r in normalized if r.get(stat_col) is not None),
            key=lambda r: r[stat_col], reverse=True,
        )[:5]
        preview = ", ".join(f"{r['player_name']}({r['position']},{r[stat_col]:.0f})" for r in top)
        log.info("top 5 %s: %s", stat_col, preview)

    snapshot_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    write_csv(normalized, snapshot_date)
    log.info("wrote %d rows -> %s", len(normalized), OUT_CSV)
    return 0


if __name__ == "__main__":
    sys.exit(main())