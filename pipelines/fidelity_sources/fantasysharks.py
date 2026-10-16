"""Fantasy Sharks rest-of-year projections reader for the fidelity pulse (JEG-621).

Independent of pipelines/pull_fantasysharks.py. Facts restated here, not imported:

  Endpoint: https://www.fantasysharks.com/apps/bert/forecasts/projections.php
            ?Segment=877 (rest of year) &Position=97 (all offense) &scoring=<id>
            with csv=1 for the CSV. Scoring ids: 1 non-PPR, 18 half-PPR, 2 PPR.
  CSV:      columns Player ID, Player Name ("Last, First"), Team, Position, Pts.
  Unit:     Pts is the rest-of-year fantasy point TOTAL. There is no games column
            (GAP-FANTASYSHARKS-ROS-TOTAL), so the unit is totals, not per game.
            A Pts of 0 means unprojected and is left out (never zero-filled).
  Vintage:  the HTML page prints "Last updated MM-DD" (no year).

Stored: public.fantasysharks_projections ros_total_non_ppr / half_ppr / ppr (totals).
Chart: Fantasy Sharks is NOT in the chart. No defensible per-game conversion
exists (the total already embeds expected missed games; dividing by team games
remaining gives points per team game, not per game played, the basis JEG-676
aligns the chart to). So stored_chart_values returns {} and the chart stage
reads "not in the live chart file" (red): the source cannot publish.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, timedelta

from fidelity_pulse import PubRow

SOURCE = "fantasysharks"
STORED_TABLE = "fantasysharks_projections"
SNAPSHOT_COLUMN = "fantasysharks_snapshot_date"
STORED_SELECT = ("player_key,player_norm,pos,team,ros_total_non_ppr,ros_total_half_ppr,ros_total_ppr,"
                 "fantasysharks_snapshot_date,created_at,pulled_at")
SAVE_STAMP = "pulled_at"
CHART_DECIMALS = 1

BASE = "https://www.fantasysharks.com/apps/bert/forecasts/projections.php"
SCORING_IDS = {"std|1": 1, "half|1": 18, "full|1": 2}
STORED_COLUMNS = {"std|1": "ros_total_non_ppr", "half|1": "ros_total_half_ppr", "full|1": "ros_total_ppr"}
POSITIONS = ("QB", "RB", "WR", "TE")
REQUIRED = ("Player ID", "Player Name", "Team", "Position", "Pts")


def url_for(scoring_id: int, as_csv: bool) -> str:
    q = f"Segment=877&Position=97&scoring={scoring_id}"
    return f"{BASE}?csv=1&{q}" if as_csv else f"{BASE}?{q}"


def display_name(raw: str) -> str:
    last, sep, first = (raw or "").partition(",")
    return f"{first.strip()} {last.strip()}".strip() if sep else (raw or "").strip()


def page_vintage(html: str, today: date) -> str | None:
    m = re.search(r"last updated\s+(\d{1,2})-(\d{1,2})", html or "", re.I)
    if not m:
        return None
    try:
        d = date(today.year, int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None
    if d > today + timedelta(days=1):
        d = date(today.year - 1, d.month, d.day)
    return d.isoformat()


def read_csv(body: str) -> tuple[list[dict] | None, str | None]:
    if not (body or "").lstrip().startswith("Rank,"):
        return None, "Fantasy Sharks body is not the projections CSV"
    reader = csv.DictReader(io.StringIO(body))
    missing = [c for c in REQUIRED if c not in (reader.fieldnames or [])]
    if missing:
        return None, f"Fantasy Sharks CSV columns gone: {missing}"
    return list(reader), None


def read_publisher(fetch) -> dict:
    from datetime import datetime, timezone  # noqa: PLC0415
    out = {"rows": [], "url": url_for(18, False), "vintage": None, "dates": {"dateModified": None},
           "notes": [], "error": None}
    status, html, _ = fetch.get(url_for(18, False))
    if status != 200 or not html:
        out["error"] = f"Fantasy Sharks page HTTP {status}"
        return out
    out["vintage"] = page_vintage(html, datetime.now(timezone.utc).date())
    if out["vintage"] is None:
        out["notes"].append("page prints no 'Last updated MM-DD' stamp")
    people: dict[str, dict] = {}
    for grain, sid in SCORING_IDS.items():
        status, body, _ = fetch.get(url_for(sid, True))
        if status != 200:
            out["error"] = f"Fantasy Sharks CSV HTTP {status} (scoring {sid})"
            return out
        rows, error = read_csv(body)
        if error:
            out["error"] = f"{error} (scoring {sid})"
            return out
        for r in rows:
            if r["Position"] not in POSITIONS:
                continue
            try:
                pts = float(r["Pts"])
            except (TypeError, ValueError):
                continue
            if pts == 0:
                continue
            p = people.setdefault(r["Player ID"], {"name": display_name(r["Player Name"]), "pos": r["Position"],
                                                   "team": r["Team"] or None, "values": {}})
            p["values"][grain] = r["Pts"].strip()
    out["rows"] = [PubRow(p["name"], p["pos"], p["team"], p["values"]) for p in people.values() if p["values"]]
    if not out["rows"]:
        out["error"] = "Fantasy Sharks lists no projected QB/RB/WR/TE rows"
    return out


def stored_publisher_values(row: dict) -> dict[str, float]:
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


def stored_chart_values(row: dict, ctx: dict) -> dict[str, float]:
    """No per-game conversion is defensible (see module docstring): nothing to compare to the chart."""
    return {}
