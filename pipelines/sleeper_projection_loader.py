#!/usr/bin/env python3
"""Loader for the fourth projection source: Sleeper weekly projections (RotoWire), 2018-2026 (JEG-949).

For research scripts (JEG-943, JEG-945). Reads local files only; changes no
shown value. gsis_id and player_key always come from the reviewed idmap
(data/inputs/sleeper_projection_idmap.csv, built by sleeper_projection_idmap.py),
never from the gsis_id column of the projections file: Sleeper's own gsis_id is
swapped for Tyler Conklin (5133) and Ryan Izzo (5094), which would join the
wrong actuals.

    from sleeper_projection_loader import load_projections, projection_actual_pairs
    rows = load_projections(seasons=range(2018, 2026), scoring="ppr")
    pairs, coverage = projection_actual_pairs(scoring="ppr", seasons=range(2018, 2026))

Rules:
- Rows whose player is not `matched`/`gsis_not_in_players` in the idmap are
  dropped from pairs and counted in coverage; nothing is guessed.
- A projected player with no actuals row is dropped and counted, never set to 0
  (nflverse writes a row when a player dressed; absence means inactive/bye).
- Timing: Sleeper `updated_at` (present from 2023) is a Monday or Tuesday, so
  pre-kickoff status of historical weeks is not proven by the file.
"""
from __future__ import annotations

import csv
import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJ = ROOT / "data/inputs/weekly_projections_sleeper.csv.gz"
IDMAP = ROOT / "data/inputs/sleeper_projection_idmap.csv"
ACT_NFLVERSE = ROOT / "data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz"
ACT_KEYED = ROOT / "data/inputs/weekly_actuals_2024_2026.csv"
SCORING_COL = {"std": "pts_std", "half_ppr": "pts_half_ppr", "ppr": "pts_ppr"}
USABLE = ("matched", "gsis_not_in_players")


def load_idmap(path: Path = IDMAP) -> dict:
    with open(path, newline="") as fh:
        return {r["sleeper_id"]: r for r in csv.DictReader(fh)}


def load_projections(seasons=None, weeks=None, scoring: str = "ppr", proj_path: Path = PROJ,
                     idmap: dict | None = None) -> list:
    """Projection rows with idmap-resolved gsis_id / player_key ('' where unresolved)."""
    col = SCORING_COL[scoring]
    idmap = load_idmap() if idmap is None else idmap
    seasons = None if seasons is None else {int(s) for s in seasons}
    weeks = None if weeks is None else {int(w) for w in weeks}
    out = []
    with gzip.open(proj_path, "rt", newline="") as fh:
        for r in csv.DictReader(fh):
            s, w = int(r["season"]), int(r["week"])
            if (seasons and s not in seasons) or (weeks and w not in weeks):
                continue
            m = idmap.get(r["sleeper_id"])
            usable = m is not None and m["status"] in USABLE
            out.append({"season": s, "week": w, "sleeper_id": r["sleeper_id"], "name": r["name"],
                        "pos": r["pos"], "team": r["team"], "projection": float(r[col]),
                        "gsis_id": m["gsis_id"] if usable else "",
                        "player_key": int(m["player_key"]) if usable and m["player_key"] else None})
    return out


def load_actuals_by_gsis(scoring: str = "ppr", path: Path = ACT_NFLVERSE) -> dict:
    """{(season, week, gsis_id): points}, nflverse 2015-2025."""
    with gzip.open(path, "rt", newline="") as fh:
        return {(int(r["season"]), int(r["week"]), r["player_id"]): float(r[scoring]) for r in csv.DictReader(fh)}


def load_actuals_by_key(scoring: str = "ppr", path: Path = ACT_KEYED) -> dict:
    """{(season, week, player_key): points}, 2024-2026 (2026 is partial)."""
    with open(path, newline="") as fh:
        return {(int(r["season"]), int(r["week"]), int(r["player_key"])): float(r[scoring]) for r in csv.DictReader(fh)}


def projection_actual_pairs(scoring: str = "ppr", seasons=None, weeks=None, via: str = "gsis",
                            rows: list | None = None, actuals: dict | None = None):
    """(projection, actual) pairs plus a coverage dict.

    via='gsis' joins nflverse actuals (2015-2025, includes players outside our players table);
    via='player_key' joins weekly_actuals_2024_2026 (the only route to 2026).
    """
    rows = load_projections(seasons, weeks, scoring) if rows is None else rows
    if actuals is None:
        actuals = load_actuals_by_gsis(scoring) if via == "gsis" else load_actuals_by_key(scoring)
    id_field = "gsis_id" if via == "gsis" else "player_key"
    pairs, cov = [], {"projection_rows": len(rows), "no_identity": 0, "no_actual_row": 0, "paired": 0}
    for r in rows:
        ident = r[id_field]
        if not ident:
            cov["no_identity"] += 1
            continue
        act = actuals.get((r["season"], r["week"], ident))
        if act is None:
            cov["no_actual_row"] += 1
            continue
        pairs.append({**r, "actual": act})
        cov["paired"] += 1
    return pairs, cov
