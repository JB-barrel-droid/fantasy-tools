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


def _int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def sort_key(row: dict) -> tuple:
    """Highest DDF Value first, missing last, then player_key."""
    v = row["value"]["ddf_value"]
    return (v is None, -(v or 0.0), row["player_key"])


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
    if not (_int(doc["season"]) and SEASON_RANGE[0] <= doc["season"] <= SEASON_RANGE[1]):
        add("$.season: not a season")
    if not (_int(doc["board_week"]) and WEEK_RANGE[0] <= doc["board_week"] <= WEEK_RANGE[1]):
        add("$.board_week: not a week 1..18")
    s = doc["setting"]
    if not isinstance(s, dict) or set(s) != set(SETTING_KEYS):
        add("$.setting: needs exactly scoring, teams, superflex")
    else:
        if s["scoring"] not in SCORINGS:
            add("$.setting.scoring: not standard, half_ppr or ppr")
        if not (_int(s["teams"]) and TEAMS_RANGE[0] <= s["teams"] <= TEAMS_RANGE[1]):
            add("$.setting.teams: out of range")
        if s["superflex"] not in (0, 1):
            add("$.setting.superflex: not 0 or 1")
    if not (isinstance(doc["points_leg"], str) and doc["points_leg"].startswith("experts.")):
        add("$.points_leg: not an experts.<name> leg id")
    for name, ref in (doc["inputs"] or {}).items():
        if not (isinstance(ref, dict) and SHA256_RE.match(str(ref.get("sha256", "")))):
            add(f"$.inputs.{name}: needs a sha256")
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
        if src["lane"] not in LANES:
            add(f"{p}.lane: not value or week")
        if src["availability"] not in AVAILABILITY:
            add(f"{p}.availability: bad value")
        if src["freshness"] is not None and src["freshness"] not in FRESHNESS:
            add(f"{p}.freshness: bad value")
        if src["label"] not in LABELS:
            add(f"{p}.label: bad value")
        if not isinstance(src["enabled"], bool):
            add(f"{p}.enabled: not a boolean")
        elif src["enabled"] == (src["disabled_reason"] is not None):
            add(f"{p}: enabled and disabled_reason disagree (a disabled source needs a reason, an enabled one has none)")
        if src["enabled"] and src["availability"] == "unavailable":
            add(f"{p}: an unavailable source cannot be enabled")
    lane_of = {**{f: "value" for f in VALUE_FIELDS}, **{f: "week" for f in WEEK_FIELDS}}
    for sid, src in sources.items():
        if isinstance(src, dict) and isinstance(src.get("feeds"), list):
            for f in src["feeds"]:
                if lane_of.get(f) not in (None, src.get("lane")):
                    add(f"$.sources.{sid}.feeds: {f} is a {lane_of[f]}-lane field on a {src.get('lane')}-lane source")
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
        _lane(row["value"], VALUE_FIELDS, sources, f"{p}.value", add)
        _lane(row["this_week"], WEEK_FIELDS, sources, f"{p}.this_week", add)
    if not out and rows != sorted(rows, key=sort_key):
        add("$.players: not sorted by DDF Value (highest first, missing last), then player_key")
    for i, row in enumerate(doc["unresolved"] or []):
        if not isinstance(row, dict) or set(row) != set(UNRESOLVED_KEYS) or not row.get("unresolved_reason"):
            add(f"$.unresolved[{i}]: needs {', '.join(UNRESOLVED_KEYS)} with a reason")
    for name in ("sections", "swaps"):
        blk = doc[name]
        if not (isinstance(blk, dict) and blk.get("available") is False and blk.get("missing_reason")):
            add(f"$.{name}: in 0.1 this is {{available: false, missing_reason}}")
    return out


def _lane(lane: Any, fields: dict, sources: dict, path: str, add) -> None:
    if not isinstance(lane, dict) or set(lane) != {*fields, "missing_reason"}:
        add(f"{path}: needs exactly {', '.join(fields)}, missing_reason")
        return
    reasons = lane["missing_reason"]
    if not isinstance(reasons, dict):
        add(f"{path}.missing_reason: not an object")
        return
    for f in reasons:
        if f not in fields:
            add(f"{path}.missing_reason.{f}: not a field of this lane")
    for f, sid in fields.items():
        v, why = lane[f], reasons.get(f)
        if v is None and not why:
            add(f"{path}.{f}: null with no reason")
        if v is not None and why:
            add(f"{path}.{f}: a value carrying a reason")
        if f in ("ddf_value", "prior_ddf_value", "change", "points") and v is not None and not _num(v):
            add(f"{path}.{f}: not a finite number")
        src = sources.get(sid)
        if isinstance(src, dict) and src.get("enabled") is False and v is not None:
            add(f"{path}.{f}: has a value although source {sid} is disabled")


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
