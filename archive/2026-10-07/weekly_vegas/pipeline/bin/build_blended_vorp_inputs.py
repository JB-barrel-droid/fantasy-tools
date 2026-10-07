#!/usr/bin/env python3
"""Build chart input tables from the canonical Sleeper season snapshot (idempotent).

Pipeline:
  1. bin/pull_sleeper_season_projections.py pulls Sleeper (rotowire)
     full-season projections -> pipeline/data/sleeper_season_projections.csv
  2. THIS script materializes two SQL tables from that CSV plus the Sleeper
     backbone identity (data/sleeper_players.json, ~12k+ players keyed by
     sleeper_player_id):
       a. sleeper_season_latest_norm (latest snapshot per player_norm,
          7 granular stats)
       b. player_canonical_map       (sleeper_player_id PK + player_norm
          -> display/position/team; replaces blended_player_map, which was
          sourced from FP)
  3. The downstream view v_blended_season_vorp joins these two tables on
     player_norm.

Identity resolution is fail-closed:
  - Every Sleeper projection row MUST resolve through sleeper_players.json
    on sleeper_player_id (the same key the pull uses). Coverage is ~100%
    because the backbone file contains every active NFL player.
  - Player rows in sleeper_players.json that aren't skill positions
    (QB/RB/WR/TE) are filtered out -- we only need skill-position volume.
  - player_norm is normalized via norm_plain (lowercase, strip punctuation).
    The 529-entry curated player_identity_map.json (alias_to_canonical) is
    consulted as a SECOND PASS to substitute the canonical display_name for
    known aliases (e.g. 'cam ward' -> 'cameron ward'). Players without a
    canonical alias keep their sleeper full_name as display_name.
  - NULL stats in the CSV stay NULL in SQL. The view's COALESCE(Vegas,
    Sleeper-fills-elsewhere) logic depends on a real NULL meaning
    "Sleeper did not project this stat" -- distinct from 0.

Data-source transition (2026-10-05): full-season FP ECR is exiting the
project. This script is the Sleeper-era replacement for the FP-sourced
build_blended_vorp_inputs.py.

Usage:
  python3 pipeline/bin/build_blended_vorp_inputs.py
"""
from __future__ import annotations

import csv
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-mgmt/bin")
from mgmt import query  # noqa: E402  (full results; CLI print truncates)

sys.path.insert(0, "/home/hatch/workspace/skills/supabase-football-signal/bin")
import sbclient  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = SCRIPT_DIR.parent
DATA_DIR = PIPELINE_DIR / "data"
INPUTS_DIR = DATA_DIR / "inputs"
SLEEPER_CSV = DATA_DIR / "sleeper_season_projections.csv"
# Sleeper backbone (12k+ players, keyed by sleeper_player_id). The brief
# describes this as "the canonical identity ... Sleeper backbone, 12k+
# players. Join on Sleeper player_id." -- the player_identity_map.json
# (529 curated skill-position entries keyed by lowercased name) is a
# SECONDARY alias map, not the join target.
_SLEEPER_BACKBONE_CANDIDATES = [
    INPUTS_DIR / "sleeper_players.json",
    Path("/home/hatch/workspace/football-signal/data/sleeper_players.json"),
]
_CANONICAL_ALIAS_CANDIDATES = [
    INPUTS_DIR / "player_identity_map.json",
    Path("/home/hatch/workspace/fantasy-tools/data/inputs/player_identity_map.json"),
]


def _resolve_first_existing(candidates):
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


SLEEPER_PLAYERS_JSON = _resolve_first_existing(_SLEEPER_BACKBONE_CANDIDATES)
IDENTITY_JSON = _resolve_first_existing(_CANONICAL_ALIAS_CANDIDATES)

SKILL_POS = {"QB", "RB", "WR", "TE"}
STAT_COLS = ["passing_yards", "passing_tds", "rushing_yards",
             "rushing_tds", "receptions", "receiving_yards",
             "receiving_tds"]

log = logging.getLogger("build_blended_vorp_inputs")


# ---------------------------------------------------------------------------
# normalization helpers (duplicated from engine/canonical_players.norm_plain
# to keep this script self-contained; single line, easy to keep in sync)
# ---------------------------------------------------------------------------
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def norm_plain(name: str) -> str:
    if not name:
        return ""
    s = name.lower()
    s = _NON_ALNUM_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ---------------------------------------------------------------------------
# SQL helpers (escape + chunked insert; same shape as the FP-era builder)
# ---------------------------------------------------------------------------
def esc(v):
    return v.replace("'", "''")


def chunked_insert(table, cols, rows, chunk=500):
    for i in range(0, len(rows), chunk):
        vals = ", ".join(
            "(" + ",".join(
                "NULL" if v is None else f"'{esc(str(v))}'" for v in r
            ) + ")" for r in rows[i:i + chunk])
        query(f"INSERT INTO {table} ({','.join(cols)}) VALUES {vals};")


# ---------------------------------------------------------------------------
# step A: pull Sleeper (delegated to the dedicated script)
# ---------------------------------------------------------------------------
def step_pull_sleeper() -> int:
    if not SLEEPER_CSV.exists():
        log.info("pulling Sleeper (CSV missing: %s)", SLEEPER_CSV)
        r = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "pull_sleeper_season_projections.py")],
            check=False,
        )
        if r.returncode != 0:
            raise SystemExit(f"sleeper pull failed (rc={r.returncode})")
    else:
        log.info("sleeper CSV already present: %s", SLEEPER_CSV)
    return _csv_count()


def _csv_count() -> int:
    with SLEEPER_CSV.open() as f:
        return sum(1 for _ in csv.DictReader(f))


# ---------------------------------------------------------------------------
# step B: load identity sources
# ---------------------------------------------------------------------------
def _load_sleeper_backbone() -> dict:
    """Return {sleeper_player_id: {full_name, position, team}} for skill pos.

    Source: data/sleeper_players.json (~12k+ players, Sleeper's own roster
    file; covers the entire NFL). This is the canonical sleeper-id-keyed
    identity table per the brief.
    """
    with SLEEPER_PLAYERS_JSON.open() as f:
        raw = json.load(f)
    out = {}
    for sid, rec in raw.items():
        pos = rec.get("position")
        if pos not in SKILL_POS:
            continue
        out[str(sid)] = {
            "full_name": (rec.get("full_name") or "").strip(),
            "position": pos,
            "team": rec.get("team"),
        }
    log.info("sleeper backbone: %d skill-position players", len(out))
    return out


def _load_canonical_aliases() -> dict:
    """Return {norm: canonical_norm} for the curated identity map.

    Source: data/inputs/player_identity_map.json (529 canonical + 592 aliases).
    Used to swap known aliases (e.g. 'cam ward' -> 'cameron ward') into the
    canonical display_name.
    """
    if not IDENTITY_JSON.exists():
        log.warning("identity map missing at %s; skipping alias pass",
                    IDENTITY_JSON)
        return {}
    with IDENTITY_JSON.open() as f:
        raw = json.load(f)
    canon = raw.get("canonical") or {}
    alias = raw.get("alias_to_canonical") or {}
    canon_display = {k: (v.get("name") or k) for k, v in canon.items()}

    out = {}
    for alias_name, canon_name in alias.items():
        an = norm_plain(alias_name)
        cn = norm_plain(canon_name)
        if cn in canon_display:
            out[an] = (cn, canon_display[cn])
    # canonical itself is its own target
    for cn, display in canon_display.items():
        out[cn] = (cn, display)
    log.info("canonical aliases: %d entries", len(out))
    return out


# ---------------------------------------------------------------------------
# step C: resolve every Sleeper projection row to (player_norm, display, ...)
# ---------------------------------------------------------------------------
def step_resolve_identity() -> tuple[list[dict], list[dict]]:
    """Load the projection CSV, join to the Sleeper backbone by sleeper_player_id,
    then map to canonical display via the alias table.

    Returns (resolved, unresolved). unresolved is for logging only; we never
    guess. A row is unresolved only if its sleeper_player_id isn't in the
    backbone file (e.g. very recent Sleeper roster additions).
    """
    backbone = _load_sleeper_backbone()
    alias_table = _load_canonical_aliases()

    with SLEEPER_CSV.open() as f:
        rows = list(csv.DictReader(f))
    log.info("projection rows loaded: %d", len(rows))

    resolved = []
    unresolved = []
    for r in rows:
        sid = r.get("sleeper_player_id")
        bb = backbone.get(sid) if sid else None
        if not bb:
            unresolved.append({"sleeper_player_id": sid,
                               "player_name": r.get("player_name"),
                               "position": r.get("position")})
            continue
        full_name = bb["full_name"] or r.get("player_name") or ""
        norm = norm_plain(full_name)
        canon_norm, canon_display = alias_table.get(norm, (norm, full_name))
        resolved.append({
            "player_norm": canon_norm,
            "sleeper_player_id": sid,
            "snapshot_date": r.get("snapshot_date"),
            "position": bb["position"] or r.get("position"),
            "team": bb["team"] or r.get("team"),
            "display_name": canon_display,
            **{c: r.get(c) for c in STAT_COLS},
            "company": r.get("company"),
        })
    log.info("identity resolution: %d resolved, %d unresolved (excluded)",
             len(resolved), len(unresolved))
    if unresolved:
        sample = unresolved[:10]
        log.warning("excluded players (sample 10 of %d): %s",
                    len(unresolved),
                    ", ".join(u["player_name"] or u["sleeper_player_id"] or 'x'
                              for u in sample))
    return resolved, unresolved


# ---------------------------------------------------------------------------
# step D: write SQL tables (idempotent)
# ---------------------------------------------------------------------------
def step_ensure_schema():
    # DDL lives in pipeline/sql/migrations/sleeper_season_latest_norm.sql,
    # applied via the Supabase SQL editor (Roman). This step only verifies
    # the tables exist before loading.
    for tbl in ("sleeper_season_latest_norm", "player_canonical_map"):
        query(f"SELECT count(*) AS n FROM {tbl} LIMIT 1")
        log.info("schema ok: %s present", tbl)


def step_load_sleeper_table(rows: list[dict]):
    """Latest snapshot per player_norm (max snapshot_date)."""
    by_norm = {}
    for r in rows:
        prev = by_norm.get(r["player_norm"])
        if prev is None or str(r["snapshot_date"]) >= str(prev["snapshot_date"]):
            by_norm[r["player_norm"]] = r
    log.info("deduped sleeper rows: %d", len(by_norm))

    query("DELETE FROM sleeper_season_latest_norm;")
    norm_rows = []
    for r in by_norm.values():
        stat_vals = []
        for c in STAT_COLS:
            v = r.get(c)
            if v in (None, ""):
                stat_vals.append(None)
            else:
                try:
                    stat_vals.append(float(v))
                except (TypeError, ValueError):
                    stat_vals.append(None)
        norm_rows.append((
            r["player_norm"], r.get("sleeper_player_id"),
            r["snapshot_date"], r["position"], r["team"],
            *stat_vals,
            r.get("company"),
        ))
    chunked_insert(
        "sleeper_season_latest_norm",
        ["player_norm", "sleeper_player_id", "snapshot_date", "position",
         "team"] + STAT_COLS + ["company"],
        norm_rows,
    )
    log.info("sleeper_season_latest_norm: %d rows", len(norm_rows))


def step_load_identity_map(rows: list[dict]):
    """Materialize player_canonical_map (replaces blended_player_map)."""
    query("DELETE FROM player_canonical_map;")
    seen = set()
    map_rows = []
    for r in rows:
        key = r["player_norm"]
        if key in seen:
            continue
        seen.add(key)
        map_rows.append((
            key, r["display_name"], r["position"], r["team"],
            r.get("sleeper_player_id"), "false",
        ))
    chunked_insert(
        "player_canonical_map",
        ["player_norm", "display_name", "position", "team",
         "sleeper_player_id", "has_vegas"],
        map_rows,
    )
    log.info("player_canonical_map: %d rows", len(map_rows))


def step_refresh_view():
    sql_path = PIPELINE_DIR / "sql" / "views" / "v_blended_season_vorp.sql"
    sql = sql_path.read_text()
    log.info("refreshing v_blended_season_vorp from %s", sql_path)
    query(sql)
    log.info("view refresh ok")


def step_audit():
    n_null_keys = query(
        "SELECT count(*) AS n FROM sleeper_season_latest_norm "
        "WHERE player_norm IS NULL;")[0]["n"]
    n_map_null = query(
        "SELECT count(*) AS n FROM player_canonical_map "
        "WHERE player_norm IS NULL;")[0]["n"]
    log.info("NULL norms: sleeper_season_latest_norm=%d, player_canonical_map=%d",
             n_null_keys, n_map_null)
    assert n_null_keys == 0 and n_map_null == 0, "NULL player_norm written"

    total = query("SELECT count(*) AS n FROM sleeper_season_latest_norm;")[0]["n"]
    if total:
        joined = query(
            "SELECT count(*) AS n FROM sleeper_season_latest_norm s "
            "JOIN player_canonical_map m USING (player_norm);")[0]["n"]
        pct = 100.0 * joined / total
        log.info("identity join rate: %d/%d = %.1f%%", joined, total, pct)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log.info("=== step 1: pull Sleeper ===")
    n_csv = step_pull_sleeper()
    log.info("sleeper CSV row count: %d", n_csv)

    log.info("=== step 2: resolve identity (sleeper backbone + alias map) ===")
    resolved, unresolved = step_resolve_identity()

    log.info("=== step 3: ensure schema ===")
    step_ensure_schema()

    log.info("=== step 4: load sleeper_season_latest_norm ===")
    step_load_sleeper_table(resolved)

    log.info("=== step 5: load player_canonical_map ===")
    step_load_identity_map(resolved)

    log.info("=== step 6: refresh view ===")
    step_refresh_view()

    log.info("=== step 7: audit ===")
    step_audit()
    log.info("done")


if __name__ == "__main__":
    main()