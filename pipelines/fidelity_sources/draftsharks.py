"""Draft Sharks trade value chart reader for the fidelity pulse (JEG-620).

Independent of pipelines/pull_draftsharks.py. Facts restated here, not imported:

  Page:  https://www.draftsharks.com/trade-value-chart server-renders one JSON
         array, `"players":[{...}]`. A row carries first_name, last_name,
         fantasy_position, abbr (team) and, per format, `dsValue<League><Scoring>`
         (Draft Sharks' own 0-100 trade value). League Redraft, Scoring NoPpr /
         HalfPpr / OnePpr feed the std / half / full grains.
  Unit:  Draft Sharks trade value, read as printed. 0 means unpriced: left out of
         that grain (never zero-filled). Negative values are real depth values.
  Vintage: the page prints no player-chart timestamp, so vintage is None and the
         pulse falls back to the stored save date.

Stored: public.draftsharks_trade_values ds_redraft_no_ppr / half_ppr / one_ppr.
Chart: Draft Sharks is NOT in the chart (no bake leg; it must stay held until
this pulse is green and a leg exists), so stored_chart_values returns {} and the
chart stage reads "not in the live chart file" (red): the source cannot publish.
"""
from __future__ import annotations

import json

from fidelity_pulse import PubRow

SOURCE = "draftsharks"
STORED_TABLE = "draftsharks_trade_values"
SNAPSHOT_COLUMN = "draftsharks_snapshot_date"
STORED_SELECT = ("player_key,player_norm,pos,team,ds_redraft_no_ppr,ds_redraft_half_ppr,ds_redraft_one_ppr,"
                 "draftsharks_snapshot_date,created_at,pulled_at")
SAVE_STAMP = "pulled_at"
CHART_DECIMALS = 1

URL = "https://www.draftsharks.com/trade-value-chart"
POSITIONS = ("QB", "RB", "WR", "TE")
PAGE_COLUMNS = {"dsValueRedraftNoPpr": "std|1", "dsValueRedraftHalfPpr": "half|1", "dsValueRedraftOnePpr": "full|1"}
STORED_COLUMNS = {"std|1": "ds_redraft_no_ppr", "half|1": "ds_redraft_half_ppr", "full|1": "ds_redraft_one_ppr"}
MIN_BODY = 1_000_000


def parse_players(body: str) -> tuple[list[dict] | None, str | None]:
    if len(body or "") < MIN_BODY:
        return None, f"Draft Sharks page is {len(body or '')} bytes (< {MIN_BODY}): bot wall or truncated"
    i = body.find('"players":')
    if i < 0:
        return None, "Draft Sharks page has no embedded players array"
    try:
        players, _ = json.JSONDecoder().raw_decode(body[i + len('"players":'):])
    except json.JSONDecodeError as e:
        return None, f"Draft Sharks players array did not parse: {e}"
    if not isinstance(players, list) or not players:
        return None, "Draft Sharks players array is empty"
    missing = [c for c in PAGE_COLUMNS if c not in players[0]]
    if missing:
        return None, f"Draft Sharks value columns gone: {missing}"
    return players, None


def read_publisher(fetch) -> dict:
    out = {"rows": [], "url": URL, "vintage": None, "dates": {"dateModified": None}, "notes": [], "error": None}
    status, body, _ = fetch.get(URL)
    if status != 200 or not body:
        out["error"] = f"Draft Sharks HTTP {status}: {URL}"
        return out
    players, error = parse_players(body)
    if error:
        out["error"] = error
        return out
    for p in players:
        pos = p.get("fantasy_position")
        if pos not in POSITIONS:
            continue
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        values = {}
        for col, grain in PAGE_COLUMNS.items():
            v = p.get(col)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and v != 0:
                values[grain] = repr(float(v)) if v != int(v) else str(int(v))
        if values and name:
            out["rows"].append(PubRow(name, pos, p.get("abbr") or None, values))
    if not out["rows"]:
        out["error"] = "Draft Sharks page lists no priced QB/RB/WR/TE rows"
    return out


def _stored(row: dict) -> dict[str, float]:
    got = {}
    for grain, col in STORED_COLUMNS.items():
        v = row.get(col)
        if v is None:
            continue
        try:
            got[grain] = float(v)
        except (TypeError, ValueError):
            continue
    return got


def stored_publisher_values(row: dict) -> dict[str, float]:
    return _stored(row)


def stored_chart_values(row: dict, ctx: dict) -> dict[str, float]:
    """No bake leg exists, so nothing is comparable to the chart (see module docstring)."""
    return {}
