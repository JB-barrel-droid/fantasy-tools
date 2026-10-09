"""CBS rest-of-season projections reader for the fidelity pulse (JEG-480).

Publisher: four position pages (QB, RB, WR, TE), each one table:
  https://www.cbssports.com/fantasy/football/stats/{POS}/2026/restofseason/projections/nonppr/
Only the nonppr page exists. Columns used, by header (abbreviation + tooltip
text, e.g. "fpts Fantasy Points"): gp (games), rec (receptions; RB/WR/TE
pages only), fpts (CBS's nonppr rest-of-season fantasy points total).

Documented scoring rule (restated from the ingest, not imported):
  standard = CBS fpts (as printed)
  half PPR = CBS fpts + 0.5 x receptions
  full PPR = CBS fpts + 1.0 x receptions
Reception points are the only scoring difference. The QB page prints no
receptions column, so a QB's half and full PPR totals equal fpts.

Stage 1 (publisher_vs_stored) unit: rest-of-season fantasy-point TOTALS.
The page prints the nonppr total; half/full are computed from the printed
fpts and receptions with exact decimal arithmetic. Stored columns:
ros_standard, ros_half_ppr, ros_ppr.

Stage 2 (stored_vs_chart) unit: per-game points. The chart's native value is
the stored per_game_* column (ROS total / gp, saved rounded to 3 decimals),
printed by the chart with 3 decimals.

Rows with gp 0 are skipped (per game is undefined; the ingest cannot store
them) and counted in a note.

The player cell flattens to "<short name> <POS> <TEAM> <full name> <POS> <TEAM>"
(e.g. "J. Allen QB BUF Josh Allen QB BUF"). The full name is taken as
printed; a cell not in that shape is reported in a note, never guessed.
"""
from __future__ import annotations

import re
import sys
from decimal import Decimal
from pathlib import Path

_PIPELINES = Path(__file__).resolve().parents[1]
if str(_PIPELINES) not in sys.path:
    sys.path.insert(0, str(_PIPELINES))

import fidelity_pulse as fp  # noqa: E402

SOURCE = "cbsros"
STORED_TABLE = "cbs_ros_projections"
SNAPSHOT_COLUMN = "cbs_snapshot_date"
STORED_SELECT = ("player_key,ros_standard,ros_half_ppr,ros_ppr,per_game_standard,per_game_half_ppr,"
                 "per_game_ppr,gp,receptions,cbs_snapshot_date,created_at")
CHART_DECIMALS = 3

BASE = "https://www.cbssports.com/fantasy/football/stats/{pos}/2026/restofseason/projections/nonppr/"
POSITIONS = ("QB", "RB", "WR", "TE")
PAGE_HEADING = {"QB": "quarterback", "RB": "running back", "WR": "wide receiver", "TE": "tight end"}

# header_key of a column -> role. Both the bare abbreviation and the
# abbreviation + tooltip text CBS prints are accepted.
HEADERS = {
    "player": ("player",),
    "gp": ("gp", "gpgamesplayed"),
    "rec": ("rec", "recreceptions"),
    "fpts": ("fpts", "fptsfantasypoints"),
}

STORED_ROS = {"std|1": "ros_standard", "half|1": "ros_half_ppr", "full|1": "ros_ppr"}
STORED_PER_GAME = {"std|1": "per_game_standard", "half|1": "per_game_half_ppr", "full|1": "per_game_ppr"}

PLAYER_CELL = re.compile(r"^(?P<short>.+?) (?P<pos>[A-Z]{1,3}) (?P<team>[A-Z]{2,4}) (?P<full>.+) (?P=pos) (?P=team)$")


def _get(fetch, url: str):
    """The framework's Fetcher (fetch.get) or a plain callable returning (status, text, url)."""
    return fetch.get(url) if hasattr(fetch, "get") else fetch(url)


def _num(text: str) -> str | None:
    cell = (text or "").replace(",", "").strip()
    return cell if fp.NUMBER.match(cell) else None


def _header_index(rows: list[list[str]]):
    """(index of the header row, {role: column}) for the first row that has a player column."""
    for i, row in enumerate(rows[:5]):
        keys = [fp.header_key(c) for c in row]
        cols = {role: next((j for j, k in enumerate(keys) if k in names), None) for role, names in HEADERS.items()}
        if cols["player"] is not None:
            return i, cols
    return None, {}


def player_cell(text: str) -> tuple[str, str, str] | None:
    """(full name, position printed in the cell, team) or None when the cell has another shape."""
    m = PLAYER_CELL.match(" ".join((text or "").split()))
    return (m.group("full"), m.group("pos"), m.group("team")) if m else None


def parse_position_page(pos: str, html: str) -> tuple[list[fp.PubRow], list[str]]:
    """Rows from one position page. Values are ROS totals: std|1, half|1, full|1."""
    _, tables = fp.parse_page(html)
    want = PAGE_HEADING[pos]
    table = next((t for t in tables if want in (t.heading or "").lower() and t.rows), None)
    if table is None:
        return [], [f"{pos}: no table under a '{want}' heading"]
    hi, cols = _header_index(table.rows)
    if hi is None:
        return [], [f"{pos}: no Player column in table '{table.heading}'"]
    missing = [r for r in ("gp", "fpts") + (() if pos == "QB" else ("rec",)) if cols.get(r) is None]
    if missing:
        return [], [f"{pos}: header lacks {', '.join(missing)}: {table.rows[hi]}"]

    rows: list[fp.PubRow] = []
    notes: list[str] = []
    bad_cells, gp_zero, no_fpts, other_pos = [], [], [], []
    for r in table.rows[hi + 1:]:
        if len(r) <= cols["player"] or not r[cols["player"]]:
            continue
        cell = player_cell(r[cols["player"]])
        if cell is None:
            bad_cells.append(r[cols["player"]])
            continue
        name, cell_pos, team = cell
        if cell_pos != pos:
            other_pos.append(f"{name} ({cell_pos})")

        def at(role):
            j = cols.get(role)
            return _num(r[j]) if j is not None and j < len(r) else None

        gp, fpts = at("gp"), at("fpts")
        if gp is not None and Decimal(gp) == 0:
            gp_zero.append(name)
            continue
        if fpts is None:
            no_fpts.append(name)
            continue
        values = {"std|1": fpts}
        rec = None if pos == "QB" else (Decimal(at("rec")) if at("rec") is not None else None)
        if pos == "QB":  # no receptions column: no reception points
            values["half|1"] = values["full|1"] = fpts
        elif rec is not None:
            base = Decimal(fpts)
            values["half|1"] = str(base + Decimal("0.5") * rec)
            values["full|1"] = str(base + rec)
        rows.append(fp.PubRow(name, pos, team, values))

    if bad_cells:
        notes.append(f"{pos}: {len(bad_cells)} player cells not in the '<short> POS TEAM <name> POS TEAM' "
                     f"shape, skipped: {bad_cells[:3]}")
    if gp_zero:
        notes.append(f"{pos}: {len(gp_zero)} players with 0 games skipped (per game undefined): {gp_zero[:5]}")
    if no_fpts:
        notes.append(f"{pos}: {len(no_fpts)} players without a numeric fpts skipped: {no_fpts[:5]}")
    if other_pos:
        notes.append(f"{pos}: {len(other_pos)} players listed with another position in the cell "
                     f"(kept as {pos}): {other_pos[:5]}")
    if not rows:
        notes.append(f"{pos}: table '{table.heading}' has no player rows")
    return rows, notes


def read_publisher(fetch) -> dict:
    rows: list[fp.PubRow] = []
    notes: list[str] = []
    failed: list[str] = []
    for pos in POSITIONS:
        url = BASE.format(pos=pos)
        status, html, _ = _get(fetch, url)
        if status != 200 or not html:
            failed.append(f"{pos} page HTTP {status}: {url}")
            continue
        got, page_notes = parse_position_page(pos, html)
        notes.extend(page_notes)
        if not got:
            failed.append(f"{pos}: no player rows parsed from {url}")
        rows.extend(got)
    main_url = BASE.format(pos="QB")
    if failed:
        # One empty position page is a page change or a block, not an empty
        # position: fail the whole read rather than compare three of four.
        return {"rows": [], "url": main_url, "vintage": None, "dates": {"dateModified": None},
                "notes": notes, "error": "; ".join(failed)}
    return {"rows": rows, "url": main_url, "vintage": None, "dates": {"dateModified": None},
            "notes": notes, "error": None}


def _numbers(row: dict, columns: dict) -> dict[str, float]:
    out = {}
    for grain, col in columns.items():
        v = row.get(col)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out[grain] = float(v)
        elif isinstance(v, str) and fp.NUMBER.match(v.strip()):
            out[grain] = float(v)
    return out


def stored_publisher_values(row: dict) -> dict[str, float]:
    """Stage 1: ROS totals (ros_standard / ros_half_ppr / ros_ppr)."""
    return _numbers(row, STORED_ROS)


def stored_chart_values(row: dict, ctx: dict) -> dict[str, float]:
    """Stage 2: per-game points, the stored per_game_* columns the chart's native values are built from."""
    return _numbers(row, STORED_PER_GAME)
