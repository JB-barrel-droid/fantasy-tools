"""Row shapes, write rule and completeness check for public.source_projection_captures (JEG-944).

Pure functions; no I/O except `write_capture` and `fetch_capture_counts`, which
take the Supabase client as an argument. Nothing here reads or changes a value
a published page shows.

What each source offers (checked 2026-10-23, docs/projection-captures.md):
  espn      one projection block per future week (every unplayed week 1-18); no
            ROS total (ROS is the sum of those weeks, not stored)
  cbs       ROS totals; a per-week page for the current week and next week only
            (weeks further out answer with the current week's page)
  razzball  ROS only (per-game columns and games); no per-week page
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

SOURCES = ("espn", "cbs", "razzball")
FORMATS = ("standard", "half_ppr", "full_ppr")
TABLE = "source_projection_captures"
CONFLICT = "source,season,source_week,horizon,target_week,player_key,scoring_format"
FINAL_WEEK = 18
# First content week every source is captured from (JEG-944, 2026-10-23).
# Earlier weeks are only the week-history backfill and are not required.
FIRST_REQUIRED_WEEK = 7
# Horizons each source must have for every required week.
REQUIRED_HORIZONS = {
    "espn": ("week",),
    "cbs": ("ros", "week"),
    "razzball": ("ros",),
}
# Fewest rows a capture may hold per (source, horizon). Far below a real pull
# (espn ~13k, cbs week ~1k, cbs ros ~1.1k, razzball ros ~1.9k): a floor that
# catches a near-empty write, not a tuning knob.
MIN_ROWS = {("espn", "week"): 3000, ("cbs", "week"): 300,
            ("cbs", "ros"): 300, ("razzball", "ros"): 300}


def capture_row(*, source, season, source_week, capture_at, horizon, target_week,
                player_key, scoring_format, basis, batch_id,
                points=None, ppg=None, games=None) -> dict:
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    if scoring_format not in FORMATS:
        raise ValueError(f"unknown scoring format {scoring_format!r}")
    if horizon == "ros":
        target_week = 0
    if points is None and ppg is None:
        raise ValueError("a capture row needs points or ppg")
    return {"source": source, "season": season, "source_week": source_week,
            "capture_at": capture_at, "horizon": horizon, "target_week": target_week,
            "player_key": player_key, "scoring_format": scoring_format,
            "points": None if points is None else round(float(points), 2),
            "ppg": None if ppg is None else round(float(ppg), 3),
            "games": None if games is None else round(float(games), 2),
            "basis": basis, "batch_id": batch_id}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_batch() -> str:
    return str(uuid.uuid4())


def dedupe(rows: list[dict]) -> list[dict]:
    """Keep the first row per unique key (two source names can resolve to one player)."""
    seen, out = set(), []
    for r in rows:
        k = tuple(r[c] for c in CONFLICT.split(","))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def _cell_params(source, season, source_week, horizon, offset):
    return (f"?select=id&source=eq.{source}&season=eq.{season}&source_week=eq.{source_week}"
            f"&horizon=eq.{horizon}&order=id&offset={offset}&limit=1")


def capture_exists(sb, source: str, season: int, source_week: int, horizon: str) -> bool:
    return bool(sb.get(TABLE, _cell_params(source, season, source_week, horizon, 0)))


def fetch_capture_counts(sb, season: int, weeks) -> dict:
    """{source: {(week, horizon): n}} without pulling the rows: n is MIN_ROWS when
    the capture holds at least that many rows, 1 when it holds fewer, absent when
    empty. One one-row query per cell (an offset probe), so the check costs a few
    dozen tiny reads, not the table."""
    out: dict = {s: {} for s in SOURCES}
    for source in SOURCES:
        for wk in weeks:
            for horizon in REQUIRED_HORIZONS[source]:
                floor = MIN_ROWS[(source, horizon)]
                if sb.get(TABLE, _cell_params(source, season, wk, horizon, floor - 1)):
                    out[source][(wk, horizon)] = floor
                elif capture_exists(sb, source, season, wk, horizon):
                    out[source][(wk, horizon)] = 1
    return out


def write_capture(sb, rows: list[dict], *, chunk: int = 500) -> int:
    """Append rows; a key already stored is left alone (first capture of a week wins)."""
    rows = dedupe(rows)
    for i in range(0, len(rows), chunk):
        sb.post(TABLE, rows[i:i + chunk], params=f"?on_conflict={CONFLICT}",
                prefer="resolution=ignore-duplicates,return=minimal")
    return len(rows)


def missing_captures(counts: dict, *, current_week: int, first_week: int = FIRST_REQUIRED_WEEK,
                     grace_current: bool = False) -> list[str]:
    """Problems with stored captures; empty list = every required capture is there.

    counts: {source: {(source_week, horizon): rows}}.
    Every week from first_week to current_week must hold, for each source, every
    required horizon with at least MIN_ROWS rows. With grace_current the current
    week may still be missing (the week's first run has not happened yet); past
    weeks never get grace.
    """
    problems = []
    last = current_week - 1 if grace_current else current_week
    for source in SOURCES:
        have = counts.get(source, {})
        for wk in range(first_week, last + 1):
            for horizon in REQUIRED_HORIZONS[source]:
                n = have.get((wk, horizon), 0)
                floor = MIN_ROWS[(source, horizon)]
                if n == 0:
                    problems.append(f"{source} {horizon} capture for content week {wk}: MISSING")
                elif n < floor:
                    problems.append(f"{source} {horizon} capture for content week {wk}: "
                                    f"{n} rows, below the floor of {floor}")
    return problems


# ------------------------------------------------- per-source row builders

_FORMAT_OF = {"standard": "standard", "half_ppr": "half_ppr", "ppr": "full_ppr"}


def cbs_capture_rows(ros_rows, weekly, resolve, *, season, source_week, capture_at,
                     batch_id, vintage):
    """CBS: ROS rows (total, per game, games) plus each offered week's totals.

    ros_rows: snapshot.json rows. weekly: weekly_snapshot.json (or None).
    resolve(name, pos, player_norm) -> player_key or None. -> (rows, report).
    """
    out, unresolved = [], 0
    for r in ros_rows:
        key = resolve(r.get("player_name"), r.get("pos"), r.get("player_norm"))
        if key is None:
            unresolved += 1
            continue
        for src_fmt, fmt in _FORMAT_OF.items():
            out.append(capture_row(
                source="cbs", season=season, source_week=source_week, capture_at=capture_at,
                horizon="ros", target_week=0, player_key=key, scoring_format=fmt,
                points=r.get(f"ros_{src_fmt}"), ppg=r.get(f"per_game_{src_fmt}"),
                games=r.get("gp"), batch_id=batch_id,
                basis=f"cbs rest-of-season page (nonppr + receptions); snapshot vintage {vintage}"))
    weeks = {}
    for wk, rows in ((weekly or {}).get("weeks") or {}).items():
        n = 0
        for r in rows:
            key = resolve(r.get("player_name"), r.get("pos"), r.get("player_norm"))
            if key is None:
                unresolved += 1
                continue
            for src_fmt, fmt in _FORMAT_OF.items():
                out.append(capture_row(
                    source="cbs", season=season, source_week=source_week, capture_at=capture_at,
                    horizon="week", target_week=int(wk), player_key=key, scoring_format=fmt,
                    points=r.get(f"points_{src_fmt}"), games=r.get("gp"), batch_id=batch_id,
                    basis=f"cbs week {wk} projection page (nonppr + receptions)"))
                n += 1
        weeks[wk] = n
    return dedupe(out), {"rows": len(dedupe(out)), "unresolved": unresolved, "week_rows": weeks,
                         "not_offered_weeks": (weekly or {}).get("not_offered_weeks"),
                         "weekly_errors": (weekly or {}).get("errors")}


def razzball_capture_rows(clean_rows, *, season, source_week, capture_at, batch_id, vintage):
    """Razzball: ROS only. clean_rows are the saver's resolved rows (per_game_*, games_reported)."""
    out = []
    for r in clean_rows:
        for src_fmt, fmt in _FORMAT_OF.items():
            ppg = r.get(f"per_game_{src_fmt}")
            if ppg is None:
                continue
            out.append(capture_row(
                source="razzball", season=season, source_week=source_week,
                capture_at=capture_at, horizon="ros", target_week=0,
                player_key=r["player_key"], scoring_format=fmt, ppg=ppg,
                games=r.get("games_reported"), batch_id=batch_id,
                basis=f"razzball rest-of-season page, published per-game column; page vintage {vintage}"))
    return dedupe(out)


def save_capture_or_flag(sb, rows, source: str, season: int, source_week: int, horizons) -> list[str]:
    """Write one source's capture, horizon by horizon, unless this content week already
    has that horizon (first one wins). Returns one line per horizon. A fault is
    returned as an '::error' annotation, never raised, so a pipeline that feeds a
    published value is not held back; check_projection_captures.py is the gate
    that fails the run."""
    lines = []
    for h in horizons:
        try:
            if capture_exists(sb, source, season, source_week, h):
                lines.append(f"capture {source} {h} week {source_week}: already stored, first one wins")
                continue
            part = [r for r in rows if r["horizon"] == h]
            if len(part) < MIN_ROWS[(source, h)]:
                raise RuntimeError(f"{len(part)} {h} rows planned, floor {MIN_ROWS[(source, h)]}; "
                                   "nothing written for this horizon")
            lines.append(f"capture {source} {h} week {source_week}: {write_capture(sb, part)} rows written")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"::error title=projection capture {source} {h}::{type(exc).__name__}: {exc}")
    return lines
