#!/usr/bin/env python3
"""Waiver-board artifact, schema `waiver-board` v0.1 (JEG-1415, slice 1 of JEG-1196).

One builder (pipelines/build_waiver_board.py) writes the board for one league
setting; the waiver board view and Bench Churn (JEG-1197) only read it. This
module is the one definition of the board's shape and the one validator for
it. Stdlib only, no network, no credentials. Contract doc:
docs/waiver-board-contract.md.

Rules it enforces:

* Two lanes, never blended. Jeremy, 2026-10-29: "do not blend weekly data with
  ROS data, ever". A row's `value` lane holds only DDF Value (rest of season)
  and its change; its `this_week` lane holds only weekly-input fields (points
  from one named expert leg, Sleeper status, bye). The key sets are fixed, so
  a field that drifts into the wrong lane is an error.
* Missing is `null` plus a reason, never zero (docs/pipeline-rules.md section 4).
  A real zero is a number with no reason.
* A disabled source disables what it feeds: every field it feeds is null on
  every row, with the source's reason.
* The enable rule is re-derived, not trusted: an enabled source is this
  season's and not for a later week; points and status must be current; DDF
  Value current or one week behind; freshness is null exactly when a source is
  unavailable; stale or previous-season content is never labelled published.
* Rows are internally consistent: change is DDF Value minus the prior DDF
  Value, on_bye agrees with bye_week, a disabled source's fields carry its reason.
* Rows are sorted by DDF Value, highest first, missing last, then player_key.
  The board sorts by Value only (design concept, "Sorting is by Value only").

Version policy: 0.x while sections, verdicts and swaps are still unbuilt
(JEG-1417, JEG-1418). A reader accepts 0.1.x only; 1.0.0 freezes the shape.

Usage:
    python3 pipelines/lib/waiver_board.py FILE [FILE ...]
Exit status 1 when any file has an error.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_NAME = "waiver-board"
SCHEMA_VERSION = "0.1.0"
READER_MAJOR, READER_MINOR = 0, 1

SCORINGS = ("standard", "half_ppr", "ppr")      # same keys as pipelines/lib/scoring.py
TEAMS_RANGE = (4, 32)
SEASON_RANGE = (2020, 2100)
WEEK_RANGE = (1, 18)
FRESHNESS = ("current", "one_week_behind", "stale", "unknown")
AVAILABILITY = ("complete", "partial", "unavailable")
LABELS = ("published", "previous-season", "modeled", "stale", "unavailable")
LANES = ("value", "week")

TOP_KEYS = ("schema", "schema_version", "season", "board_week", "built_at", "producer", "setting",
            "points_leg", "inputs", "sources", "players", "unresolved", "sections", "swaps")
SETTING_KEYS = ("scoring", "teams", "superflex")
SOURCE_KEYS = ("lane", "source", "availability", "freshness", "label", "content_season", "content_week",
               "content_vintage", "enabled", "disabled_reason", "feeds")
ROW_KEYS = ("player_key", "name", "position", "team", "value", "this_week")
UNRESOLVED_KEYS = ("name", "position", "team", "unresolved_reason")
# Each lane's fields and the source that feeds each one. A field is null with a
# reason (missing_reason[field]) or a value with no reason, never both.
VALUE_FIELDS = {"ddf_value": "values", "prior_ddf_value": "values_prior", "change": "values_prior"}
WEEK_FIELDS = {"points": "points", "status": "status", "injury_status": "status",
               "practice_participation": "status", "bye_week": "bye", "on_bye": "bye"}
# Sources every board declares. `points` is the named expert leg (top-level points_leg);
# rostered_pct and kickoff are not in weekly-inputs 1.0.0 yet (JEG-1416).
REQUIRED_SOURCES = ("values", "values_prior", "points", "status", "bye", "rostered_pct", "kickoff")
SOURCE_ID_RE = re.compile(r"^(values|values_prior|points|status|bye|rostered_pct|kickoff|vegas|experts\.[a-z][a-z0-9_]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class BoardError(ValueError):
    pass


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


_int = is_int


def _reason(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _iso_with_offset(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    try:
        from timestamps import parse_iso_timestamp
    except ImportError:   # run as a script: pipelines/lib is this file's directory
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from timestamps import parse_iso_timestamp
    try:
        return parse_iso_timestamp(v).tzinfo is not None
    except ValueError:
        return False


def sort_key(row: dict) -> tuple:
    """Highest DDF Value first, missing last, then player_key."""
    v = row["value"]["ddf_value"]
    return (v is None, -(v or 0.0), row["player_key"])


def expected_feeds(sid: str) -> list[str]:
    """The fields a source feeds: its own lane's map, nothing for a listed-only leg."""
    return [f for fields in (VALUE_FIELDS, WEEK_FIELDS) for f, src in fields.items() if src == sid]


def validate(doc: Any) -> list[str]:
    """Every problem in a board document, as "path: message". Empty means valid."""
    out: list[str] = []
    add = out.append
    if not isinstance(doc, dict):
        return ["$: not a JSON object"]
    for k in TOP_KEYS:
        if k not in doc:
            add(f"$.{k}: missing")
    for k in doc:
        if k not in TOP_KEYS:
            add(f"$.{k}: unknown field")
    if out:
        return out
    if doc["schema"] != SCHEMA_NAME:
        add("$.schema: not waiver-board")
    m = VERSION_RE.match(str(doc["schema_version"]))
    if not m or (int(m.group(1)), int(m.group(2))) != (READER_MAJOR, READER_MINOR):
        add(f"$.schema_version: {doc['schema_version']!r} is not {READER_MAJOR}.{READER_MINOR}.x")
    season_ok = _int(doc["season"]) and SEASON_RANGE[0] <= doc["season"] <= SEASON_RANGE[1]
    if not season_ok:
        add("$.season: not a season")
    week_ok = _int(doc["board_week"]) and WEEK_RANGE[0] <= doc["board_week"] <= WEEK_RANGE[1]
    if not week_ok:
        add("$.board_week: not a week 1..18")
    if not _iso_with_offset(doc["built_at"]):
        add("$.built_at: not an ISO 8601 timestamp with a UTC offset")
    if not _reason(doc["producer"]):
        add("$.producer: not a non-empty string")
    s = doc["setting"]
    if not isinstance(s, dict) or set(s) != set(SETTING_KEYS):
        add("$.setting: needs exactly scoring, teams, superflex")
    else:
        if s["scoring"] not in SCORINGS:
            add("$.setting.scoring: not standard, half_ppr or ppr")
        if not (_int(s["teams"]) and TEAMS_RANGE[0] <= s["teams"] <= TEAMS_RANGE[1]):
            add("$.setting.teams: out of range")
        if not (_int(s["superflex"]) and s["superflex"] in (0, 1)):
            add("$.setting.superflex: not 0 or 1")
    if not (isinstance(doc["points_leg"], str) and SOURCE_ID_RE.match(doc["points_leg"])
            and doc["points_leg"].startswith("experts.")):
        add("$.points_leg: not an experts.<name> leg id")
    if not isinstance(doc["inputs"], dict):
        add("$.inputs: not an object")
    else:
        for name, ref in doc["inputs"].items():
            if not (isinstance(ref, dict) and isinstance(ref.get("name"), str)
                    and SHA256_RE.match(str(ref.get("sha256", "")))):
                add(f"$.inputs.{name}: needs a name and a sha256")
    sources = doc["sources"]
    if not isinstance(sources, dict):
        return out + ["$.sources: not an object"]
    for sid in REQUIRED_SOURCES:
        if sid not in sources:
            add(f"$.sources.{sid}: missing")
    for sid, src in sources.items():
        p = f"$.sources.{sid}"
        if not SOURCE_ID_RE.match(sid):
            add(f"{p}: unknown source id")
        if not isinstance(src, dict) or set(src) != set(SOURCE_KEYS):
            add(f"{p}: needs exactly {', '.join(SOURCE_KEYS)}")
            continue
        _source(sid, src, sources, doc, p, add, season_ok and week_ok)
    rows = doc["players"]
    if not isinstance(rows, list):
        return out + ["$.players: not a list"]
    seen: set = set()
    for i, row in enumerate(rows):
        p = f"$.players[{i}]"
        if not isinstance(row, dict) or set(row) != set(ROW_KEYS):
            add(f"{p}: needs exactly {', '.join(ROW_KEYS)}")
            continue
        if not _int(row["player_key"]):
            add(f"{p}.player_key: not an integer (unresolved rows go in $.unresolved)")
        elif row["player_key"] in seen:
            add(f"{p}.player_key: duplicate {row['player_key']}")
        seen.add(row["player_key"])
        for k in ("name", "position", "team"):
            if row[k] is not None and not isinstance(row[k], str):
                add(f"{p}.{k}: not a string or null")
        # Cross-field checks run only on a lane whose shape passed, so a missing key is reported, never raised.
        if _lane(row["value"], VALUE_FIELDS, sources, f"{p}.value", add):
            _value_row(row["value"], f"{p}.value", add)
        if _lane(row["this_week"], WEEK_FIELDS, sources, f"{p}.this_week", add):
            _week_row(row["this_week"], doc["board_week"] if week_ok else None, f"{p}.this_week", add)
    if not out and rows != sorted(rows, key=sort_key):
        add("$.players: not sorted by DDF Value (highest first, missing last), then player_key")
    if not isinstance(doc["unresolved"], list):
        add("$.unresolved: not a list")
    else:
        for i, row in enumerate(doc["unresolved"]):
            if not isinstance(row, dict) or set(row) != set(UNRESOLVED_KEYS) or not _reason(row.get("unresolved_reason")):
                add(f"$.unresolved[{i}]: needs {', '.join(UNRESOLVED_KEYS)} with a reason")
    for name in ("sections", "swaps"):
        blk = doc[name]
        if not (isinstance(blk, dict) and set(blk) == {"available", "missing_reason"} and blk["available"] is False
                and _reason(blk["missing_reason"])):
            add(f"$.{name}: in 0.1 this is {{available: false, missing_reason}}")
    return out


# Sources the board may turn on; any other listed leg feeds nothing and stays off in 0.1.
BOARD_SOURCES = ("values", "values_prior", "points", "status", "bye")


def _source(sid: str, src: dict, sources: dict, doc: dict, p: str, add, header_ok: bool) -> None:
    """One source's fields and its enable rule, re-derived (the builder's rule, docs/waiver-board-contract.md)."""
    if src["lane"] not in LANES:
        add(f"{p}.lane: not value or week")
    elif sid in BOARD_SOURCES and src["lane"] != ("value" if sid in ("values", "values_prior") else "week"):
        add(f"{p}.lane: {sid} is a {'value' if sid in ('values', 'values_prior') else 'week'}-lane source")
    if src["availability"] not in AVAILABILITY:
        add(f"{p}.availability: bad value")
    if src["freshness"] is not None and src["freshness"] not in FRESHNESS:
        add(f"{p}.freshness: bad value")
    if src["label"] not in LABELS:
        add(f"{p}.label: bad value")
    if (src["freshness"] is None) != (src["availability"] == "unavailable"):
        add(f"{p}.freshness: null exactly when the source is unavailable (unknown when its age is unknown)")
    if (src["availability"] == "unavailable") != (src["label"] == "unavailable"):
        add(f"{p}.label: labelled unavailable exactly when the source is unavailable")
    if src["freshness"] == "stale" and src["label"] == "published":
        add(f"{p}.label: stale content is labelled stale, not published")
    for k in ("content_season", "content_week"):
        if src[k] is not None and not _int(src[k]):
            add(f"{p}.{k}: not an integer or null")
    if src["content_week"] is not None and _int(src["content_week"]) \
            and not WEEK_RANGE[0] <= src["content_week"] <= WEEK_RANGE[1]:
        add(f"{p}.content_week: not a week 1..18")
    season = doc["season"]
    if header_ok and _int(src["content_season"]) and src["content_season"] < season and src["label"] == "published":
        add(f"{p}.label: season {src['content_season']} content on a season {season} board is not published")
    if header_ok and src["label"] == "previous-season" and not (_int(src["content_season"])
                                                               and src["content_season"] < season):
        add(f"{p}.label: previous-season is only for content from a season before {season}")
    if header_ok and sid in ("values", "values_prior") and src["availability"] != "unavailable":
        want = _value_freshness(sid, src, sources, doc)
        if want is not None and src["freshness"] != want:
            add(f"{p}.freshness: {src['freshness']} disagrees with its weeks (expected {want})")
    for k in ("source", "content_vintage"):
        if src[k] is not None and not isinstance(src[k], str):
            add(f"{p}.{k}: not a string or null")
    if not isinstance(src["feeds"], list):
        add(f"{p}.feeds: not a list")
    else:
        lane_of = {**{f: "value" for f in VALUE_FIELDS}, **{f: "week" for f in WEEK_FIELDS}}
        for f in src["feeds"]:
            if lane_of.get(f) not in (None, src["lane"]):
                add(f"{p}.feeds: {f} is a {lane_of[f]}-lane field on a {src['lane']}-lane source")
    if isinstance(src["feeds"], list) and SOURCE_ID_RE.match(sid):
        want = expected_feeds(sid)   # the named points leg feeds through source `points`, not its own id
        if sorted(src["feeds"]) != sorted(want):
            add(f"{p}.feeds: {sid} feeds {', '.join(want) or 'nothing'}")
    if not isinstance(src["enabled"], bool):
        add(f"{p}.enabled: not a boolean")
        return
    if src["enabled"] == (src["disabled_reason"] is not None):
        add(f"{p}: enabled and disabled_reason disagree (a disabled source needs a reason, an enabled one has none)")
    if src["disabled_reason"] is not None and not _reason(src["disabled_reason"]):
        add(f"{p}.disabled_reason: not a non-empty string")
    if not src["enabled"]:
        return
    if src["availability"] == "unavailable":
        add(f"{p}: an unavailable source cannot be enabled")
    if sid not in BOARD_SOURCES:
        add(f"{p}: only {', '.join(BOARD_SOURCES)} can be enabled in 0.1")
        return
    if not header_ok:
        return
    board_week = doc["board_week"]
    if src["content_season"] != season:
        add(f"{p}: enabled with season {src['content_season']} content on a season {season} board")
    if _int(src["content_week"]) and src["content_week"] > board_week:
        add(f"{p}: enabled with week {src['content_week']} content on a week {board_week} board")
    if sid in ("points", "status") and src["freshness"] != "current":
        add(f"{p}: a weekly leg is enabled only when current (got {src['freshness']})")
    if sid in ("points", "status") and src["content_week"] != board_week:
        add(f"{p}: a current weekly leg is for the board week")
    if sid in ("values", "values_prior") and src["freshness"] not in ("current", "one_week_behind"):
        add(f"{p}: DDF Value is enabled only when current or one week behind (got {src['freshness']})")
    if sid == "values" and not _int(src["content_week"]):
        add(f"{p}: enabled DDF Value needs its content week")
    if sid == "values_prior":
        vals = sources.get("values")
        if not (isinstance(vals, dict) and vals.get("enabled") is True):
            add(f"{p}: the prior DDF Value is enabled only with DDF Value")
        elif not (_int(vals.get("content_week")) and src["content_week"] == vals["content_week"] - 1):
            add(f"{p}.content_week: the prior DDF Value is the week before DDF Value's week")


def freshness_for_weeks(board_week: int, week: int | None) -> str:
    """The weekly contract's rule (weekly_inputs_contract.freshness_for_weeks): 0 behind current,
    1 behind one_week_behind, else stale."""
    if week is None:
        return "unknown"
    behind = board_week - week
    return "current" if behind <= 0 else "one_week_behind" if behind == 1 else "stale"


def _value_freshness(sid: str, src: dict, sources: dict, doc: dict) -> str | None:
    """What a value source's freshness must be. DDF Value: its own week against the board week (another
    season is stale). The prior pair: that of the DDF Value it pairs with, or its own week's with none."""
    if sid == "values_prior":
        vals = sources.get("values")
        if isinstance(vals, dict) and vals.get("availability") not in (None, "unavailable"):
            return vals.get("freshness")
    if not _int(src["content_season"]) or not _int(src["content_week"]):
        return None
    if src["content_season"] != doc["season"]:
        return "stale"
    return freshness_for_weeks(doc["board_week"], src["content_week"])


def _lane(lane: Any, fields: dict, sources: dict, path: str, add) -> bool:
    """Checks one lane; True when its shape is whole (every field and a missing_reason object)."""
    if not isinstance(lane, dict) or set(lane) != {*fields, "missing_reason"}:
        add(f"{path}: needs exactly {', '.join(fields)}, missing_reason")
        return False
    reasons = lane["missing_reason"]
    if not isinstance(reasons, dict):
        add(f"{path}.missing_reason: not an object")
        return False
    for f, why in reasons.items():
        if f not in fields:
            add(f"{path}.missing_reason.{f}: not a field of this lane")
        elif not _reason(why):
            add(f"{path}.missing_reason.{f}: not a non-empty string")
    for f, sid in fields.items():
        v, why = lane[f], reasons.get(f)
        if v is None and why is None:
            add(f"{path}.{f}: null with no reason")
        if v is not None and why is not None:
            add(f"{path}.{f}: a value carrying a reason")
        if f in ("ddf_value", "prior_ddf_value", "change", "points") and v is not None and not _num(v):
            add(f"{path}.{f}: not a finite number")
        if f in ("status", "injury_status", "practice_participation") and v is not None and not isinstance(v, str):
            add(f"{path}.{f}: not a string")
        src = sources.get(sid)
        if isinstance(src, dict) and src.get("enabled") is False:
            if v is not None:
                add(f"{path}.{f}: has a value although source {sid} is disabled")
            elif why is not None and why != src.get("disabled_reason"):
                add(f"{path}.missing_reason.{f}: not source {sid}'s disabled reason")
    return True


def _value_row(lane: dict, path: str, add) -> None:
    ddf, prior, change = lane["ddf_value"], lane["prior_ddf_value"], lane["change"]
    if change is None:
        if _num(ddf) and _num(prior):
            add(f"{path}.change: missing although DDF Value and the prior DDF Value are both there")
    elif not (_num(ddf) and _num(prior)):
        add(f"{path}.change: a change needs both DDF Value and the prior DDF Value")
    elif _num(change) and not math.isclose(change, ddf - prior, rel_tol=0.0, abs_tol=1e-9):
        add(f"{path}.change: {change} is not DDF Value minus the prior DDF Value ({ddf - prior})")


def _week_row(lane: dict, board_week: int | None, path: str, add) -> None:
    bye, on_bye = lane["bye_week"], lane["on_bye"]
    if bye is not None and not (_int(bye) and WEEK_RANGE[0] <= bye <= WEEK_RANGE[1]):
        add(f"{path}.bye_week: not a week 1..18")
    if on_bye is not None and not isinstance(on_bye, bool):
        add(f"{path}.on_bye: not a boolean")
    if (bye is None) != (on_bye is None):
        add(f"{path}.on_bye: present exactly when bye_week is")
    elif _int(bye) and isinstance(on_bye, bool) and board_week is not None and on_bye != (bye == board_week):
        add(f"{path}.on_bye: disagrees with bye_week {bye} on a week {board_week} board")


def validate_file(path: str | Path) -> list[str]:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"$: cannot read: {exc}"]
    return validate(doc)


def main(argv: list[str] | None = None) -> int:
    paths = sys.argv[1:] if argv is None else argv
    bad = 0
    for p in paths:
        problems = validate_file(p)
        for msg in problems:
            print(f"{p}: {msg}")
        bad += bool(problems)
        if not problems:
            print(f"{p}: ok")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
