#!/usr/bin/env python3
"""Offline waiver-board builder (JEG-1415, slice 1 of JEG-1196).

Joins two inputs for one league setting into the `waiver-board` v0.1 artifact
(`pipelines/lib/waiver_board.py`, `docs/waiver-board-contract.md`):

  weekly inputs   a `weekly-inputs` 1.x artifact (JEG-1227 contract, written by
                  pipelines/build_weekly_inputs.py). Refused unless the JEG-1227
                  validator passes it.
  DDF Value       per player at the setting, rest of season. Either a values
                  snapshot file (`--values`, shape below) or the Python
                  reference run read-only on the published inputs
                  (`--from-reference`: pipelines/value_reference.py, Adjusted
                  view, `ddf_value`, the engine's twin that value_check diffs
                  against the page). The board prices nobody itself.

Two lanes, never blended (Jeremy, 2026-10-29: "do not blend weekly data with
ROS data, ever"):

  value      DDF Value, the reference's prior-week DDF Value at the same
             setting (like-for-like: last week's inputs through today's math),
             and Change = DDF Value - prior. Read from the DDF Value input only.
  this_week  points from one named weekly expert leg at the setting's scoring,
             Sleeper status and bye. Read from the weekly inputs only. Context:
             nothing in this slice sorts or decides on it.

Every source keeps the weekly contract's availability, freshness and label. A
source that is unavailable, stale, one week behind (for weekly legs), of
unknown age or from another season is disabled: every field it feeds is null
with the source's reason. Missing stays null with a reason, never zero.

Offline only: explicit local inputs, explicit output path, no network, no
Supabase, no wall clock (`--built-at` is the clock). Same inputs give the same
bytes. Rostered %, kickoff times, sections, verdicts and swaps are declared
unavailable with a reason (JEG-1416 to JEG-1418).

Usage:
  python3 pipelines/build_waiver_board.py --weekly-inputs inputs-wk8.json \\
      --scoring half_ppr --teams 12 [--superflex 0] \\
      --built-at 2026-10-30T12:00:00Z --out /tmp/waiver-board.json \\
      (--values values.json | --from-reference [--chart-fixture F --players F --history DIR]) \\
      [--points-leg experts.espn_weekly] [--values-out values.json]

Values snapshot (`--values`, and what `--values-out` writes):
  {"kind": "ddf-values", "version": 1, "source": str, "source_version": str|null,
   "view": "adj", "series": "ddf_value", "setting": {scoring, teams, superflex},
   "season": int, "content_week": int, "content_vintage": str|null, "label": str,
   "inputs": [{"name", "sha256"}],
   "players": {"<player_key>": {"name", "position", "team", "ddf_value": number}},
   "prior": {"available": bool, "week": int|null, "values": {"<player_key>": number},
             "missing_reason": str|null}}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import waiver_board as wb  # noqa: E402
import weekly_inputs_contract as wic  # noqa: E402
from timestamps import parse_iso_timestamp  # noqa: E402

PRODUCER = "pipelines/build_waiver_board.py"
DEFAULT_POINTS_LEG = "experts.espn_weekly"
VALUES_KIND, VALUES_VERSION = "ddf-values", 1
NOT_PRICED_POS = ("K", "DST")
STATUS_FIELDS = ("status", "injury_status", "practice_participation")
FRESHNESS_WORDS = {"current": "current", "one_week_behind": "one week behind", "stale": "stale",
                   "unknown": "of unknown age"}
SECTIONS_REASON = ("sections and ADD, PASS, HOLD and DROP verdicts are not built yet (JEG-1417); "
                   "they need rostered % (JEG-1416) and a rule Jeremy picks")
SWAPS_REASON = "roster-matched swaps are not built yet (JEG-1418)"
NOT_IN_CONTRACT = "not in the weekly-input contract 1.0.0 yet (JEG-1416)"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _canonical_key(key) -> bool:
    """A player_key written the one way: "101", never "0101" or "+101"."""
    return isinstance(key, str) and key.isdigit() and str(int(key)) == key


# ------------------------------------------------------------------ inputs

def load_weekly(text: str) -> dict:
    """The weekly-inputs document, or BoardError when the JEG-1227 validator finds an error."""
    issues = wic.validate_text(text)
    bad = wic.errors(issues)
    if bad:
        raise wb.BoardError("weekly inputs fail the weekly-input contract: "
                            + "; ".join(str(i) for i in bad[:5]))
    return json.loads(text)


def check_values(snap: dict, setting: dict) -> dict:
    """A values snapshot, checked; BoardError on a malformed one or another setting."""
    if not isinstance(snap, dict) or snap.get("kind") != VALUES_KIND or snap.get("version") != VALUES_VERSION:
        raise wb.BoardError(f"values input is not a {VALUES_KIND} v{VALUES_VERSION} snapshot")
    vset = snap.get("setting")
    if (not isinstance(vset, dict) or set(vset) != set(wb.SETTING_KEYS)
            or any(isinstance(v, bool) for v in vset.values()) or vset != setting):
        raise wb.BoardError(f"values are for setting {vset}, the board is for {setting}")
    for k in ("season", "content_week"):
        if not isinstance(snap.get(k), int) or isinstance(snap.get(k), bool):
            raise wb.BoardError(f"values input has no integer {k}")
    if snap.get("label") not in wb.LABELS:
        raise wb.BoardError("values input has no valid label")
    players = snap.get("players")
    if not isinstance(players, dict):
        raise wb.BoardError("values input has no players object")
    for key, p in players.items():
        if not _canonical_key(key) or not isinstance(p, dict) or not _finite(p.get("ddf_value")):
            raise wb.BoardError(f"values input row {key!r} needs an integer player_key and a finite ddf_value")
    prior = snap.get("prior")
    if not isinstance(prior, dict) or not isinstance(prior.get("available"), bool):
        raise wb.BoardError("values input has no prior block")
    if prior["available"]:
        if (not isinstance(prior.get("values"), dict) or not isinstance(prior.get("week"), int)
                or isinstance(prior.get("week"), bool)):
            raise wb.BoardError("values input prior is available but has no week or values")
        for key, v in prior["values"].items():
            if not _canonical_key(key) or not _finite(v):
                raise wb.BoardError(f"values input prior row {key!r} is not a finite number")
    elif not prior.get("missing_reason"):
        raise wb.BoardError("values input prior is unavailable with no reason")
    return snap


def values_from_reference(setting: dict, today: date, fixture: Path | None = None, players: Path | None = None,
                          history: Path | None = None) -> dict:
    """A values snapshot from pipelines/value_reference.py at the setting, read-only on the published inputs."""
    import nfl_week
    import value_reference as ref
    fixture = Path(fixture or ref.FIXTURE)
    players = Path(players or ref.PLAYERS)
    history = Path(history or ref.HISTORY)
    inp = ref.Inputs.load(fixture, players, today=today)
    hist = ref.History(history)
    fresh = ref.freshness(inp)
    # Divergence exclusions are keyed by the calendar week, as value_reference.main loads them.
    out = ref.compute(inp, setting, hist=hist,
                      divergence_exclusions=ref.load_divergence_exclusions(week=fresh["current_week"]))
    team_of = {}
    pl_doc = json.loads(players.read_text(encoding="utf-8"))
    for p in pl_doc.get("players") or []:
        if isinstance(p.get("player_key"), int) and not isinstance(p.get("player_key"), bool):
            team_of[p["player_key"]] = p.get("team")
    rows = {}
    for k, row in out["views"]["adj"].items():
        v = row.get(ref.COMPOSITE_KEY)
        key = int(k)
        if not _finite(v) or key not in inp.players:
            continue
        info = inp.players[key]
        rows[str(key)] = {"name": info["name"], "position": info["pos"], "team": team_of.get(key),
                          "ddf_value": v}
    pr = (out.get("prior") or {}).get("adj", {}).get(ref.COMPOSITE_KEY) or {}
    # The week the reference priced, not the build day's calendar week: with a matching history it is
    # the served week of its prior pair (the page's week view); without one, the newest week the
    # weekly charts serve (capped at the calendar week), else the calendar week.
    if pr.get("available"):
        week = pr["currentWeek"]
        prior = {"available": True, "week": pr["priorWeek"], "missing_reason": None,
                 "values": {str(int(k)): v for k, v in pr["values"].items() if _finite(v)}}
    else:
        week = fresh["reference_week"] if fresh["reference_week"] is not None else fresh["current_week"]
        prior = {"available": False, "week": None, "values": {},
                 "missing_reason": (f"the reference has no week {week - 1} DDF Value at this setting (it needs "
                                    f"the week history `make sync` writes, from the same build, in {history.name}/)")}
    return {
        "kind": VALUES_KIND, "version": VALUES_VERSION, "source": "value_reference",
        "source_version": ref.VERSION, "view": "adj", "series": ref.COMPOSITE_KEY,
        "setting": dict(setting), "season": nfl_week.SEASON, "content_week": week,
        "content_vintage": (pl_doc.get("meta") or {}).get("as_of"), "label": "published",
        "inputs": [{"name": fixture.name, "sha256": _sha256(fixture.read_bytes())},
                   {"name": players.name, "sha256": _sha256(players.read_bytes())}],
        "players": dict(sorted(rows.items(), key=lambda kv: int(kv[0]))),
        "prior": prior,
    }


# ------------------------------------------------------------------ sources

def _src(lane, source, availability, freshness, label, season, week, vintage, reason, feeds) -> dict:
    return {"lane": lane, "source": source, "availability": availability, "freshness": freshness,
            "label": label, "content_season": season, "content_week": week, "content_vintage": vintage,
            "enabled": reason is None, "disabled_reason": reason, "feeds": list(feeds)}


def _weekly_reason(leg_id: str, leg: dict, season: int, board_week: int, aged: bool) -> str | None:
    """Why a weekly leg is disabled on this board, or None. aged: the leg must be this week's (points,
    status); a season table (bye) need only be this season's."""
    if leg["availability"] == "unavailable":
        return leg.get("missing_reason") or f"{leg_id} is unavailable"
    if leg["content_season"] != season:
        return f"{leg_id} is season {leg['content_season']} data; the board is season {season}"
    if aged and leg["freshness"] != "current":
        word = FRESHNESS_WORDS.get(leg["freshness"], str(leg["freshness"]))
        wk = leg["content_week"]
        return f"{leg_id} is {word} (content week {wk if wk is not None else 'unknown'}, board week {board_week})"
    return None


def _weekly_source(leg_id: str, leg: dict, season: int, board_week: int, aged: bool, feeds, extra: str | None = None):
    reason = _weekly_reason(leg_id, leg, season, board_week, aged) or extra
    return _src("week", leg["source"], leg["availability"], leg["freshness"], leg["label"],
                leg["content_season"], leg["content_week"], leg["content_vintage"], reason, feeds)


def _prior_freshness(prior: dict, vfresh: str | None, vseason: int, season: int, board_week: int) -> str | None:
    """The prior pair is as fresh as the DDF Value it is paired with (its content week is the week
    before); with no current side, its own week's age."""
    if not prior["available"]:
        return None
    if vfresh is not None:
        return vfresh
    return wic.freshness_for_weeks(board_week, prior["week"]) if vseason == season else "stale"


def build_sources(weekly: dict, values: dict, setting: dict, points_leg: str) -> dict:
    season, board_week = weekly["season"], weekly["content_week"]
    legs = weekly["legs"]
    out = {}
    # Value lane: rest-of-season DDF Value. One week behind is still a fair ROS price; stale is not.
    vweek = values["content_week"]
    vavail = "complete" if values["players"] else "unavailable"
    # Freshness compares weeks within one season; across seasons a price is stale (the contract's rule).
    vfresh = (None if vavail == "unavailable" else
              wic.freshness_for_weeks(board_week, vweek) if values["season"] == season else "stale")
    if values["season"] != season:
        vreason = f"DDF Value is season {values['season']} data; the board is season {season}"
        vlabel = "previous-season" if values["season"] < season else values["label"]
    elif vweek > board_week:
        vreason = f"DDF Value is for week {vweek}, later than the board week {board_week}"
        vlabel = values["label"]
    elif vfresh == "stale":
        vreason = f"DDF Value is stale (content week {vweek}, board week {board_week})"
        vlabel = "stale"
    elif not values["players"]:
        vreason = "the DDF Value input prices no player at this setting"
        vlabel = "unavailable"
    else:
        vreason, vlabel = None, values["label"]
    if vlabel == "published" and vfresh == "stale":
        vlabel = "stale"
    out["values"] = _src("value", values["source"], vavail, vfresh, vlabel, values["season"], vweek,
                         values.get("content_vintage"), vreason, ["ddf_value"])
    prior = values["prior"]
    if vreason is not None:
        preason = f"DDF Value is disabled: {vreason}"
    elif not prior["available"]:
        preason = prior["missing_reason"]
    elif prior["week"] != vweek - 1:
        preason = f"the prior DDF Value is week {prior['week']}, not week {vweek - 1}"
    else:
        preason = None
    out["values_prior"] = _src("value", values["source"], "complete" if prior["available"] else "unavailable",
                               _prior_freshness(prior, vfresh, values["season"], season, board_week),
                               ("unavailable" if not prior["available"] else
                                vlabel if vlabel != "unavailable" else values["label"]),
                               values["season"], prior.get("week"), values.get("content_vintage"),
                               preason, ["prior_ddf_value", "change"])
    # This-week lane: weekly-input legs.
    if points_leg not in legs:
        raise wb.BoardError(f"points leg {points_leg} is not in the weekly inputs (legs: {', '.join(sorted(legs))})")
    pleg = legs[points_leg]
    if pleg["kind"] != "expert" or pleg["units"] != "fantasy_points":
        raise wb.BoardError(f"points leg {points_leg} is not an expert leg in fantasy points")
    scoring_gap = (None if setting["scoring"] in (pleg.get("scoring") or [])
                   else f"{points_leg} has no {setting['scoring']} points")
    out["points"] = _weekly_source(points_leg, pleg, season, board_week, True, ["points"], scoring_gap)
    for sid, aged, feeds in (("status", True, STATUS_FIELDS), ("bye", False, ["bye_week", "on_bye"])):
        if sid in legs:
            out[sid] = _weekly_source(sid, legs[sid], season, board_week, aged, feeds)
        else:   # the contract allows a file without this leg
            out[sid] = _src("week", None, "unavailable", None, "unavailable", None, None, None,
                            f"the {sid} leg is not in the weekly inputs", feeds)
    for leg_id in sorted(legs):
        if leg_id in (points_leg, "status", "bye"):
            continue
        leg = legs[leg_id]
        unused = _weekly_reason(leg_id, leg, season, board_week, True) or "not used by the waiver board yet"
        out[leg_id] = _src("week", leg["source"], leg["availability"], leg["freshness"], leg["label"],
                           leg["content_season"], leg["content_week"], leg["content_vintage"], unused, [])
    for sid in ("rostered_pct", "kickoff"):
        out[sid] = _src("week", None, "unavailable", None, "unavailable", None, None, None, NOT_IN_CONTRACT, [])
    return out


# ------------------------------------------------------------------ rows

def _cell_reason(cell: dict | None, field: str, leg_id: str) -> str:
    if cell is None:
        return f"no {leg_id} row for this player"
    why = cell.get("missing_reason")
    if isinstance(why, dict) and why.get(field):
        return why[field]
    if isinstance(why, str) and why:
        return why
    return f"{leg_id} has no {field} for this player"


def _value_lane(key: int, position: str | None, values: dict, sources: dict) -> dict:
    lane = {"ddf_value": None, "prior_ddf_value": None, "change": None, "missing_reason": {}}
    why = lane["missing_reason"]
    vsrc, psrc = sources["values"], sources["values_prior"]
    row = values["players"].get(str(key))
    if not vsrc["enabled"]:
        why["ddf_value"] = vsrc["disabled_reason"]
    elif row is None:
        why["ddf_value"] = ("DDF Value does not price kickers or defenses" if position in NOT_PRICED_POS
                            else "not priced by DDF Value at this setting")
    else:
        lane["ddf_value"] = row["ddf_value"]
    if not psrc["enabled"]:
        why["prior_ddf_value"] = why["change"] = psrc["disabled_reason"]
        return lane
    prior = values["prior"]["values"].get(str(key))
    if prior is None:
        why["prior_ddf_value"] = f"no DDF Value in week {values['prior']['week']}"
    else:
        lane["prior_ddf_value"] = prior
    if lane["ddf_value"] is None or prior is None:
        why["change"] = why.get("ddf_value") or why["prior_ddf_value"]
    else:
        lane["change"] = lane["ddf_value"] - prior
    return lane


def _week_lane(wrow: dict | None, board_week: int, setting: dict, points_leg: str, sources: dict) -> dict:
    lane = {f: None for f in wb.WEEK_FIELDS}
    lane["missing_reason"] = why = {}
    legs = (wrow or {}).get("legs") or {}
    absent = "not in the weekly inputs"
    # points
    if not sources["points"]["enabled"]:
        why["points"] = sources["points"]["disabled_reason"]
    elif wrow is None:
        why["points"] = absent
    else:
        cell = legs.get(points_leg)
        v = ((cell or {}).get("values") or {}).get(setting["scoring"])
        if v is None:
            why["points"] = _cell_reason(cell, setting["scoring"], points_leg)
        else:
            lane["points"] = v
    # status
    for f in STATUS_FIELDS:
        if not sources["status"]["enabled"]:
            why[f] = sources["status"]["disabled_reason"]
        elif wrow is None:
            why[f] = absent
        else:
            cell = legs.get("status")
            v = ((cell or {}).get("values") or {}).get(f)
            if v is None:
                why[f] = _cell_reason(cell, f, "status")
            else:
                lane[f] = v
    # bye
    if not sources["bye"]["enabled"]:
        why["bye_week"] = why["on_bye"] = sources["bye"]["disabled_reason"]
    elif wrow is None:
        why["bye_week"] = why["on_bye"] = absent
    else:
        cell = legs.get("bye")
        v = ((cell or {}).get("values") or {}).get("bye_week")
        if v is None:
            why["bye_week"] = why["on_bye"] = _cell_reason(cell, "bye_week", "bye")
        else:
            lane["bye_week"] = v
            lane["on_bye"] = v == board_week
    return lane


def build_board(weekly: dict, values: dict, setting: dict, built_at: str, points_leg: str = DEFAULT_POINTS_LEG,
                inputs: dict | None = None) -> dict:
    """The waiver-board document. weekly: a validated weekly-inputs doc. values: a checked snapshot."""
    if (not isinstance(setting, dict) or set(setting) != set(wb.SETTING_KEYS)
            or setting["scoring"] not in wb.SCORINGS or not wb.is_int(setting["teams"])
            or setting["superflex"] not in (0, 1) or isinstance(setting["superflex"], bool)):
        raise wb.BoardError(f"setting {setting!r} needs scoring (standard, half_ppr, ppr), integer teams "
                            "and superflex 0 or 1")
    major = (wic.parse_version(weekly.get("schema_version")) or (None,))[0]
    if major != 1:
        raise wb.BoardError(f"weekly inputs schema {weekly.get('schema_version')!r} is not 1.x")
    check_values(values, setting)
    sources = build_sources(weekly, values, setting, points_leg)
    board_week = weekly["content_week"]
    weekly_rows, unresolved = {}, []
    for r in weekly["players"]:
        if r["player_key"] is None:
            unresolved.append({"name": r["name"], "position": r["position"], "team": r["team"],
                               "unresolved_reason": r.get("unresolved_reason") or "no player_key"})
        else:
            weekly_rows[r["player_key"]] = r
    keys = set(weekly_rows) | {int(k) for k in values["players"]}
    rows = []
    for key in keys:
        wrow, vrow = weekly_rows.get(key), values["players"].get(str(key)) or {}
        base = wrow or vrow
        rows.append({
            "player_key": key, "name": base.get("name"), "position": base.get("position"),
            "team": base.get("team"),
            "value": _value_lane(key, base.get("position"), values, sources),
            "this_week": _week_lane(wrow, board_week, setting, points_leg, sources),
        })
    rows.sort(key=wb.sort_key)
    unresolved.sort(key=lambda u: (str(u["name"]), str(u["team"]), str(u["unresolved_reason"])))
    doc = {
        "schema": wb.SCHEMA_NAME, "schema_version": wb.SCHEMA_VERSION,
        "season": weekly["season"], "board_week": board_week, "built_at": built_at, "producer": PRODUCER,
        "setting": dict(setting), "points_leg": points_leg, "inputs": inputs or {},
        "sources": sources, "players": rows, "unresolved": unresolved,
        "sections": {"available": False, "missing_reason": SECTIONS_REASON},
        "swaps": {"available": False, "missing_reason": SWAPS_REASON},
    }
    problems = wb.validate(doc)
    if problems:
        raise wb.BoardError("built board fails its own schema: " + "; ".join(problems[:5]))
    return doc


def dumps(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _parse_built_at(text: str) -> datetime:
    try:
        dt = parse_iso_timestamp(text)
    except ValueError as exc:
        raise wb.BoardError(f"--built-at {text!r} is not ISO 8601") from exc
    if dt.tzinfo is None:
        raise wb.BoardError("--built-at needs a UTC offset")
    return dt


def _new_york_day(dt: datetime) -> date:
    import nfl_week
    return nfl_week.today_ny(dt.astimezone(timezone.utc))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--weekly-inputs", type=Path, required=True)
    p.add_argument("--scoring", choices=wb.SCORINGS, required=True)
    p.add_argument("--teams", type=int, required=True)
    p.add_argument("--superflex", type=int, choices=(0, 1), default=0)
    p.add_argument("--built-at", required=True, help="ISO timestamp with zone; the only clock")
    p.add_argument("--out", type=Path, required=True)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--values", type=Path, help="a ddf-values snapshot file")
    src.add_argument("--from-reference", action="store_true",
                     help="price with pipelines/value_reference.py on the published inputs (read-only)")
    p.add_argument("--chart-fixture", type=Path, help="--from-reference: comparison-sources-data.json")
    p.add_argument("--players", type=Path, help="--from-reference: published players.json")
    p.add_argument("--history", type=Path, help="--from-reference: week history directory")
    p.add_argument("--points-leg", default=DEFAULT_POINTS_LEG, help="the weekly expert leg for This week points")
    p.add_argument("--values-out", type=Path, help="also write the values snapshot used")
    a = p.parse_args(argv)
    setting = {"scoring": a.scoring, "teams": a.teams, "superflex": a.superflex}
    try:
        built = _parse_built_at(a.built_at)
        wbytes = a.weekly_inputs.read_bytes()
        weekly = load_weekly(wbytes.decode("utf-8"))
        if a.from_reference:
            values = values_from_reference(setting, _new_york_day(built), a.chart_fixture, a.players, a.history)
            vname, vbytes = "value_reference", dumps(values).encode("utf-8")
        else:
            vbytes = a.values.read_bytes()
            values = json.loads(vbytes)
            vname = a.values.name
        inputs = {"weekly_inputs": {"name": a.weekly_inputs.name, "sha256": _sha256(wbytes)},
                  "values": {"name": vname, "sha256": _sha256(vbytes)}}
        doc = build_board(weekly, values, setting, a.built_at, a.points_leg, inputs)
    except (OSError, ValueError, wb.BoardError) as exc:
        print(f"build_waiver_board: refused, nothing written: {exc}", file=sys.stderr)
        return 2
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(dumps(doc), encoding="utf-8")
    if a.values_out:
        a.values_out.parent.mkdir(parents=True, exist_ok=True)
        a.values_out.write_bytes(vbytes)   # the bytes inputs.values.sha256 covers
    enabled = sorted(k for k, s in doc["sources"].items() if s["enabled"])
    print(f"wrote {a.out}: {len(doc['players'])} players, {len(doc['unresolved'])} unresolved, "
          f"week {doc['board_week']} {setting['scoring']}/{setting['teams']}/sf{setting['superflex']}, "
          f"sources on: {', '.join(enabled) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
