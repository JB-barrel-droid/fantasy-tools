"""Razzball rest-of-season projections reader for the fidelity pulse (JEG-480).

Independent of pipelines/pull_razzball_ros.py: the pages are walked with
fidelity_pulse.parse_page and keyed on header text. Facts learned from the
ingest (restated here, not imported):

  Pages: https://football.razzball.com/projections-{qb,rb,wr,te}-restofseason/
  Table: the largest table whose header has both "Name" and "STD PPG" (each
         page also carries a small "#/Name/Team/Pos/PTS/G" sidebar table and
         navigation tables; neither has PPG columns).
  Unit:  points per game, Razzball's published "STD PPG", "1/2 PPR PPG" and
         "PPR PPG" columns, read verbatim.
  Doubling quirk: on some vintages Razzball prints the Games column and the
         counting totals at 2x. The published PPG columns are the canonical
         per-game values (2x totals / 2x games cancels), so this reader never
         divides a total by Games; it reads the PPG columns as printed.
  QB rule: the QB page prints STD PPG only. A QB earns no reception points,
         so half PPR PPG = PPR PPG = STD PPG (the stored QB rows carry
         per_game_standard == per_game_half_ppr == per_game_ppr).
  Vintage: each page prints "Updated: YYYY-MM-DD hh:mm:ss PM EST". The vintage
         is the date of the OLDEST of the four stamps (the oldest page bounds
         how fresh the read is); dateModified is the NEWEST stamp as a
         timestamp, taken as printed in EST (UTC-05:00).

Stored (stage 1): public.razzball_projections per_game_standard /
per_game_half_ppr / per_game_ppr are those published PPG columns.
Chart (stage 2): sources.razzball.combos.<scoring>_12.native is the DDF leg's
"ppg", which is the same published PPG column at full precision, so the
chart's native value equals the stored per-game value; the chart prints it
with 1 decimal.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fidelity_pulse import NUMBER, PubRow, header_key, parse_page

SOURCE = "razzball"
STORED_TABLE = "razzball_projections"
SNAPSHOT_COLUMN = "razzball_snapshot_date"
STORED_SELECT = ("player_key,pos,team,per_game_standard,per_game_half_ppr,per_game_ppr,"
                 "games_reported,razzball_snapshot_date,created_at")
CHART_DECIMALS = 1

URL = "https://football.razzball.com/projections-{pos}-restofseason/"
POSITIONS = ("QB", "RB", "WR", "TE")

# header_key of the published per-game column -> grain.
PPG_COLUMNS = {"stdppg": "std|1", "12pprppg": "half|1", "pprppg": "full|1"}
STORED_COLUMNS = {"std|1": "per_game_standard", "half|1": "per_game_half_ppr", "full|1": "per_game_ppr"}

STAMP_RE = re.compile(r"Updated:?\s*(\d{4}-\d{2}-\d{2})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([AP]M)", re.I)
EST = timezone(timedelta(hours=-5))


def page_stamp(html: str) -> datetime | None:
    """Razzball's own 'Updated: YYYY-MM-DD hh:mm:ss PM EST' stamp (tags stripped)."""
    m = STAMP_RE.search(re.sub(r"<[^>]+>", " ", html or ""))
    if not m:
        return None
    day, hh, mm, ss, ampm = m.groups()
    hour = int(hh) % 12 + (12 if ampm.upper() == "PM" else 0)
    try:
        return datetime.fromisoformat(day).replace(hour=hour, minute=int(mm), second=int(ss), tzinfo=EST)
    except ValueError:
        return None


def page_position(title: str, heading: str) -> str | None:
    """The position the page says it lists ('2026 QB Fantasy Football Projections')."""
    hits = {p for p in POSITIONS for text in (heading, title) if re.search(rf"\b{p}\b", text or "")}
    return hits.pop() if len(hits) == 1 else None


def projections_table(tables):
    """(table, header keys) of the largest table carrying Name and STD PPG, or (None, None)."""
    best = None
    for t in tables:
        if not t.rows:
            continue
        keys = [header_key(h) for h in t.rows[0]]
        if "name" in keys and "stdppg" in keys and (best is None or len(t.rows) > len(best[0].rows)):
            best = (t, keys)
    return best or (None, None)


def read_page(pos: str, html: str) -> tuple[list[PubRow], list[str], str | None]:
    """Rows of one position page. Returns (rows, notes, error)."""
    title, tables = parse_page(html)
    table, keys = projections_table(tables)
    if table is None:
        return [], [], f"{pos} page: no table with both a Name and a STD PPG column"
    page_pos = page_position(title, table.heading)
    if page_pos != pos:
        return [], [], f"{pos} page says it lists {page_pos or 'no single position'} ({table.heading!r})"
    i_name = keys.index("name")
    i_team = keys.index("team") if "team" in keys else None
    cols = {i: PPG_COLUMNS[k] for i, k in enumerate(keys) if k in PPG_COLUMNS}
    notes: list[str] = []
    if pos != "QB" and len(cols) != 3:
        return [], [], f"{pos} page: expected STD, 1/2 PPR and PPR PPG columns, header {table.rows[0]}"
    i_pts = keys.index("stdpts") if "stdpts" in keys else None
    i_games = next((keys.index(k) for k in ("games", "g") if k in keys), None)
    rows: list[PubRow] = []
    skipped = off = 0
    for r in table.rows[1:]:
        name = r[i_name].strip() if i_name < len(r) else ""
        if not name or header_key(name) == "name":
            continue
        values = {}
        for i, grain in cols.items():
            cell = r[i].strip() if i < len(r) else ""
            if NUMBER.match(cell):
                values[grain] = cell
        if pos == "QB" and "std|1" in values:
            # Documented QB rule: no reception points, so every scoring is STD PPG.
            values["half|1"] = values["full|1"] = values["std|1"]
        if len(values) < len(cols):
            skipped += 1
        # Layout sanity, not a correction: STD PTS / Games should reproduce the
        # printed STD PPG whether or not Games and totals are doubled.
        if i_pts is not None and i_games is not None and "std|1" in values:
            try:
                pts, games = float(r[i_pts]), float(r[i_games])
                if games > 0 and abs(pts / games - float(values["std|1"])) > 0.1:
                    off += 1
            except (ValueError, IndexError):
                pass
        rows.append(PubRow(name, pos, r[i_team].strip() or None if i_team is not None and i_team < len(r) else None,
                           values))
    if skipped:
        notes.append(f"{pos}: {skipped} rows with a missing or non-numeric PPG cell (left out of those scorings)")
    if off:
        notes.append(f"{pos}: {off} rows where STD PTS / Games disagrees with the printed STD PPG by > 0.1")
    if not rows:
        return [], notes, f"{pos} page: projections table has no player rows"
    return rows, notes, None


def read_publisher(fetch) -> dict:
    rows: list[PubRow] = []
    notes: list[str] = []
    stamps: dict[str, datetime] = {}
    main_url = URL.format(pos="qb")
    for pos in POSITIONS:
        url = URL.format(pos=pos.lower())
        status, html, _ = fetch.get(url)
        if status != 200 or not html:
            return {"rows": [], "url": url, "vintage": None, "dates": {"dateModified": None}, "notes": notes,
                    "error": f"Razzball {pos} page HTTP {status}: {url}"}
        got, page_notes, error = read_page(pos, html)
        notes += page_notes
        if error:
            return {"rows": [], "url": url, "vintage": None, "dates": {"dateModified": None}, "notes": notes,
                    "error": error}
        rows += got
        stamp = page_stamp(html)
        if stamp is None:
            notes.append(f"{pos} page prints no 'Updated: <date>' stamp")
        else:
            stamps[pos] = stamp
    if len({s.date() for s in stamps.values()}) > 1:
        notes.append("pages carry different Updated stamps: "
                     + ", ".join(f"{p} {s:%Y-%m-%d %H:%M}" for p, s in stamps.items()))
    vintage = min(stamps.values()).date().isoformat() if stamps else None
    modified = max(stamps.values()).isoformat() if stamps else None
    return {"rows": rows, "url": main_url, "vintage": vintage, "dates": {"dateModified": modified},
            "notes": notes, "error": None}


def _per_game(row: dict) -> dict[str, float]:
    out = {}
    for grain, col in STORED_COLUMNS.items():
        v = row.get(col)
        if v is None:
            continue
        try:
            out[grain] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def stored_publisher_values(row: dict) -> dict[str, float]:
    """Stage 1: the stored per-game columns are Razzball's published PPG columns."""
    return _per_game(row)


def stored_chart_values(row: dict, ctx: dict) -> dict[str, float]:
    """Stage 2: the chart's native value is the DDF leg's ppg, i.e. the same
    published PPG column (full precision, printed with CHART_DECIMALS)."""
    return _per_game(row)
