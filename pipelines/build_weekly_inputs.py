#!/usr/bin/env python3
"""Offline weekly-input producer (JEG-1228, slice S2 of JEG-1195).

Turns explicit stored weekly inputs into the versioned `weekly-inputs-v1`
artifact (contract: JEG-1227, `pipelines/lib/weekly_inputs_contract.py`):

  experts.espn_weekly  ESPN weekly projections CSV (the shape of
                       data/inputs/espn_weekly_projections_2026.csv)
  status               an export of public.player_status_history rows (JSON list)
  bye                  the bye table (the shape of data/inputs/nfl_byes_2026.json)
  experts.ecr_weekly   no producer yet (S3b): always unavailable here
  vegas                no producer yet (S3): always unavailable here

Offline only: every input is a local path given on the command line, the
output path is explicit, and nothing reads the network, Supabase or the wall
clock (`--as-of` is the clock). Same inputs give the same bytes.

Rules it keeps (docs/pipeline-rules.md §4-5, Jeremy 2026-10-29):
  - Weekly only. A rest-of-season input is refused and nothing is written
    ("do not blend weekly data with ROS data, ever").
  - Missing stays null with a reason; 0.0 is a value, never "missing".
  - Partial rows stay in, marked partial. Unresolved players stay in with
    player_key null and the reason, never guessed.
  - Availability (is there data) and freshness (how old is its content week)
    are separate fields. Freshness is content vintage, never pull time.
  - Only the target season and week are used; rows for another week, another
    season or after --as-of are counted in input_report and left out.

Usage:
  python3 pipelines/build_weekly_inputs.py --season 2026 --week 8 \\
      --as-of 2026-10-29T02:00:00Z --out /tmp/inputs-wk8.json \\
      [--espn-weekly FILE.csv] [--status FILE.json] [--byes FILE.json] \\
      [--players FILE.json] [--sleeper-base FILE.json]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from nfl_week import NEW_YORK, content_week_or_none  # noqa: E402
from timestamps import parse_iso_timestamp  # noqa: E402

SCHEMA = "weekly-inputs-v1"
PRODUCER = "pipelines/build_weekly_inputs.py"
SCORINGS = ("std", "half_ppr", "ppr")
LEG_IDS = ("experts.espn_weekly", "experts.ecr_weekly", "vegas", "status", "bye")
# The Sleeper fields public.player_status_history stores, unchanged
# (pipelines/save_player_status_history.py FIELDS).
STATUS_FIELDS = ("status", "injury_status", "injury_body_part", "injury_start_date",
                 "practice_participation", "depth_chart_position", "depth_chart_order")
ESPN_REQUIRED = ("season", "week", "player_key", "std", "half_ppr", "ppr", "snapshot_at")
# Column names that only a rest-of-season file carries (the ESPN ROS CSV:
# ros_half_ppr, weeks_covered, season_block_half_ppr, r_* stat totals).
ROS_COLUMN_PREFIXES = ("ros", "r_", "weeks_covered", "season_block", "weeks_remaining")
UNAVAILABLE_REASONS = {
    "experts.ecr_weekly": "no weekly ECR producer yet (JEG-1195 slice S3b)",
    "vegas": "no Vegas producer yet (JEG-1195 slice S3)",
}


class InputError(Exception):
    """An input this producer refuses outright; nothing is written."""


# ---------------------------------------------------------------- helpers

def _iso_utc(value: str) -> datetime:
    moment = parse_iso_timestamp(str(value).strip())
    if moment.tzinfo is None:
        raise ValueError(f"timestamp without a zone: {value!r}")
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ny_day(moment: datetime) -> date:
    return moment.astimezone(NEW_YORK).date()


def _int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _num(value):
    """Blank -> None; a number (0.0 included) -> float; junk -> None."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _file_meta(path: Path) -> dict:
    return {"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _freshness(target_week: int, vintage_week: int | None) -> str:
    """The existing vocabulary (pipelines/check_reference_freshness.py)."""
    if vintage_week is None:
        return "unknown"
    behind = max(target_week - vintage_week, 0)
    return "current" if behind == 0 else ("one_week_behind" if behind == 1 else "stale")


def _leg_meta(source, *, inputs=(), units=None, scorings=None):
    return {"source": source, "availability": "unavailable", "freshness": None,
            "label": "unavailable", "content_week": None, "content_vintage": None,
            "units": units, "scorings": list(scorings) if scorings else None,
            "unavailable_reason": None, "inputs": list(inputs)}


def _mark_available(meta, target_week, vintage_day: date | None, vintage: str | None, availability):
    """Freshness from the content week of the newest capture (content vintage)."""
    vweek = content_week_or_none(vintage_day) if vintage_day else None
    meta["availability"] = availability
    meta["freshness"] = _freshness(target_week, vweek)
    meta["label"] = "stale" if meta["freshness"] == "stale" else "published"
    meta["content_week"] = target_week
    meta["content_vintage"] = vintage


def _cell(value=None, reason=None, captured_at=None, provenance=None):
    return {"value": value, "missing_reason": None if value is not None else reason,
            "captured_at": captured_at, "provenance": provenance}


class Identity:
    """Canonical keys through the existing helpers (pipelines/lib/player_key_index.py)."""

    def __init__(self, players_path: Path | None, sleeper_base_path: Path | None):
        self.index = None
        self.known: dict[int, dict] | None = None
        if players_path is None:
            return
        rows = json.loads(players_path.read_text())
        if isinstance(rows, dict):
            rows = rows.get("players") or rows.get("rows") or []
        norm = []
        for r in rows:
            md = dict(r.get("metadata") or {})
            for k in ("gsis_id", "sleeper_id"):
                if r.get(k) and not md.get(k):
                    md[k] = r[k]
            norm.append({**r, "metadata": md, "active": r.get("active", True)})
        base = json.loads(sleeper_base_path.read_text()) if sleeper_base_path else {}
        from player_key_index import PlayerIndex  # noqa: PLC0415
        self.index = PlayerIndex(norm, base)
        self.known = self.index.by_key

    def check_key(self, key: int):
        """-> (key, None) or (None, reason) when a players snapshot was given."""
        if self.known is None or key in self.known:
            return key, None
        return None, f"player_key {key} not in players snapshot"

    def resolve_sleeper(self, sleeper_id, name, pos):
        if self.index is None:
            return None, "status row has no player_key and no players snapshot was given"
        e, how = self.index.resolve_sleeper(sleeper_id, name or "", (pos or "").upper())
        return (e["player_key"], "player_index:" + how) if e else (None, f"unresolved: {how}")

    def name(self, key):
        e = (self.known or {}).get(key)
        return e["full_name"] if e else None


# ---------------------------------------------------------------- readers

def _reject_ros_header(path: Path, header: list[str]):
    for col in header:
        low = col.strip().lower()
        if low.startswith(ROS_COLUMN_PREFIXES) or "_ros" in low:
            raise InputError(f"{path.name}: column {col!r} is rest-of-season; "
                             "weekly inputs never take ROS data")


def read_espn(path: Path, season: int, week: int, as_of: datetime, ident: Identity, report):
    meta = _leg_meta("espn", inputs=[_file_meta(path)], units="fantasy_points", scorings=SCORINGS)
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        _reject_ros_header(path, header)
        missing = [c for c in ESPN_REQUIRED if c not in header]
        if missing:
            raise InputError(f"{path.name}: missing columns {missing}")
        raw = list(enumerate(reader, start=2))
    candidates: dict[tuple, list] = {}
    for line, r in raw:
        report["read"] += 1
        horizon = (r.get("horizon") or "week").strip().lower()
        if horizon != "week":
            raise InputError(f"{path.name} line {line}: horizon {horizon!r}; "
                             "weekly inputs never take ROS data")
        if _int(r["season"]) != season:
            report["wrong_season"] += 1
            continue
        if _int(r["week"]) != week:
            report["wrong_week"] += 1
            continue
        try:
            snap = _iso_utc(r["snapshot_at"])
        except ValueError:
            report["bad_row"] += 1
            continue
        if snap > as_of:
            report["after_as_of"] += 1
            continue
        key = _int(r["player_key"])
        ident_key = ("key", key) if key is not None else ("espn_row", str(line))
        candidates.setdefault(ident_key, []).append((snap, line, r))
    if not candidates:
        meta["unavailable_reason"] = f"no rows for season {season} week {week} on or before --as-of"
        return meta, {}
    rows, vintage, partial = {}, None, False
    for ident_key, cands in candidates.items():
        cands.sort(key=lambda c: (c[0], c[1]))
        newest = cands[-1][0]
        top = [c for c in cands if c[0] == newest]
        if len(cands) > 1:
            report["duplicate"] += len(cands) - 1
        vintage = newest if vintage is None or newest > vintage else vintage
        values = [{s: _num(c[2][s]) for s in SCORINGS} for c in top]
        r = top[-1][2]
        info = {"position": (r.get("pos") or "").upper() or None, "team": r.get("team") or None,
                "source_ids": {}, "resolved_by": None, "unresolved_reason": None}
        key = ident_key[1] if ident_key[0] == "key" else None
        if key is None:
            info["source_ids"]["espn_row"] = ident_key[1]
            info["unresolved_reason"] = "espn row has no player_key"
        else:
            info["source_ids"]["espn_player_key"] = key
            key, why = ident.check_key(key)
            info["resolved_by"] = "espn_weekly.player_key" if key is not None else None
            info["unresolved_reason"] = why
        if any(v != values[0] for v in values[1:]):
            report["conflict"] += 1
            cell = _cell(reason="conflicting duplicate rows at the same snapshot",
                         captured_at=_stamp(newest))
            partial = True
        else:
            v = values[0]
            present = [s for s in SCORINGS if v[s] is not None]
            if not present:
                cell = _cell(reason="no projection values", captured_at=_stamp(newest))
                partial = True
            else:
                prov = "complete" if len(present) == len(SCORINGS) else "partial"
                partial = partial or prov == "partial"
                cell = _cell(v, captured_at=_stamp(newest), provenance=prov)
        rows[_row_id(key, info)] = (key, info, cell)
    _mark_available(meta, week, _ny_day(vintage), _stamp(vintage), "partial" if partial else "complete")
    return meta, rows


def read_status(path: Path, week: int, as_of: datetime, ident: Identity, report):
    meta = _leg_meta("sleeper", inputs=[_file_meta(path)])
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("rows") or []
    as_of_day = _ny_day(as_of)
    usable = []
    for r in data:
        report["read"] += 1
        if (r.get("horizon") or "week") != "week":
            raise InputError(f"{path.name}: horizon {r.get('horizon')!r}; "
                             "weekly inputs never take ROS data")
        try:
            day = date.fromisoformat(str(r.get("snapshot_date") or "")[:10])
        except ValueError:
            report["bad_row"] += 1
            continue
        if day > as_of_day:
            report["after_as_of"] += 1
            continue
        cw = content_week_or_none(day)
        if cw is None or cw > week:
            report["wrong_week"] += 1
            continue
        usable.append((day, r))
    if not usable:
        meta["unavailable_reason"] = f"no status snapshot in or before week {week} on or before --as-of"
        return meta, {}
    latest = max(d for d, _ in usable)
    report["older_snapshot"] += sum(1 for d, _ in usable if d != latest)
    by_sid: dict[str, list] = {}
    for _, r in (x for x in usable if x[0] == latest):
        by_sid.setdefault(str(r.get("sleeper_id") or ""), []).append(r)
    captured = latest.isoformat()
    rows, partial = {}, False
    for sid in sorted(by_sid):
        group = by_sid[sid]
        if len(group) > 1:
            report["duplicate"] += len(group) - 1
        values = [{f: r.get(f) for f in STATUS_FIELDS} for r in group]
        r = group[0]
        info = {"position": (r.get("position") or "").upper() or None, "team": r.get("team") or None,
                "name": r.get("full_name") or None, "source_ids": {"sleeper_id": sid},
                "resolved_by": None, "unresolved_reason": None}
        key = _int(r.get("player_key"))
        if key is not None:
            key, why = ident.check_key(key)
            info["resolved_by"] = "status.player_key" if key is not None else None
            info["unresolved_reason"] = why
        else:
            key, how = ident.resolve_sleeper(sid, info["name"], info["position"])
            info["resolved_by" if key is not None else "unresolved_reason"] = how
        if any(v != values[0] for v in values[1:]):
            report["conflict"] += 1
            partial = True
            cell = _cell(reason="conflicting duplicate status rows", captured_at=captured)
        else:
            cell = _cell(values[0], captured_at=captured, provenance="complete")
        rid = _row_id(key, info)
        if rid in rows:
            # Two Sleeper ids on one player_key: keep neither value.
            report["conflict"] += 1
            partial = True
            prev = rows[rid]
            prev[1]["source_ids"]["sleeper_id"] = ",".join(
                sorted({prev[1]["source_ids"]["sleeper_id"], sid}))
            rows[rid] = (key, prev[1], _cell(reason="two sleeper ids for one player_key",
                                             captured_at=captured))
            continue
        rows[rid] = (key, info, cell)
    _mark_available(meta, week, latest, captured, "partial" if partial else "complete")
    return meta, rows


def read_byes(path: Path, season: int, week: int):
    meta = _leg_meta("nfl_byes", inputs=[_file_meta(path)])
    data = json.loads(path.read_text())
    if _int(data.get("season")) != season or not isinstance(data.get("byes"), dict):
        meta["unavailable_reason"] = f"bye table is not for season {season}"
        return meta, None
    byes = {str(t).upper(): _int(w) for t, w in data["byes"].items()}
    meta.update(availability="complete", freshness="current", label="published",
                content_week=week)
    return meta, byes


def _row_id(key, info):
    if key is not None:
        return (0, f"{key:012d}")
    ids = info["source_ids"]
    return (1, "|".join(f"{k}={ids[k]}" for k in sorted(ids)))


# ---------------------------------------------------------------- build

def build(args) -> dict:
    as_of = _iso_utc(args.as_of)
    counts = ("read", "wrong_season", "wrong_week", "after_as_of", "older_snapshot",
              "duplicate", "conflict", "bad_row")
    report = {leg: {k: 0 for k in counts} for leg in ("experts.espn_weekly", "status")}
    report["unresolved_rows"] = 0
    ident = Identity(args.players, args.sleeper_base)
    legs = {
        "experts.espn_weekly": _leg_meta("espn", units="fantasy_points", scorings=SCORINGS),
        "experts.ecr_weekly": _leg_meta("fantasypros_ecr", units="fantasy_points", scorings=SCORINGS),
        "vegas": _leg_meta("propline", units="fantasy_points", scorings=SCORINGS),
        "status": _leg_meta("sleeper"),
        "bye": _leg_meta("nfl_byes"),
    }
    for leg, why in UNAVAILABLE_REASONS.items():
        legs[leg]["unavailable_reason"] = why
    per_leg: dict[str, dict] = {}
    if args.espn_weekly:
        legs["experts.espn_weekly"], per_leg["experts.espn_weekly"] = read_espn(
            args.espn_weekly, args.season, args.week, as_of, ident, report["experts.espn_weekly"])
    else:
        legs["experts.espn_weekly"]["unavailable_reason"] = "input not supplied"
    if args.status:
        legs["status"], per_leg["status"] = read_status(args.status, args.week, as_of, ident, report["status"])
    else:
        legs["status"]["unavailable_reason"] = "input not supplied"
    byes = None
    if args.byes:
        legs["bye"], byes = read_byes(args.byes, args.season, args.week)
    else:
        legs["bye"]["unavailable_reason"] = "input not supplied"

    merged: dict[tuple, dict] = {}
    for leg in ("experts.espn_weekly", "status"):
        for rid, (key, info, cell) in per_leg.get(leg, {}).items():
            row = merged.setdefault(rid, {"player_key": key, "infos": {}, "cells": {}})
            row["infos"][leg] = info
            row["cells"][leg] = cell

    out_rows = []
    for rid in sorted(merged):
        row = merged[rid]
        espn_i = row["infos"].get("experts.espn_weekly") or {}
        stat_i = row["infos"].get("status") or {}
        key = row["player_key"]
        team = espn_i.get("team") or stat_i.get("team")
        reasons = [i["unresolved_reason"] for i in (espn_i, stat_i) if i.get("unresolved_reason")]
        if key is None:
            report["unresolved_rows"] += 1
        identity = {
            "name": (ident.name(key) if key is not None else None) or stat_i.get("name"),
            "position": espn_i.get("position") or stat_i.get("position"),
            "team": team,
            "resolved_by": espn_i.get("resolved_by") or stat_i.get("resolved_by"),
            "unresolved_reason": "; ".join(reasons) if key is None and reasons else None,
            "source_ids": {**stat_i.get("source_ids", {}), **espn_i.get("source_ids", {})},
        }
        cells = {}
        for leg in LEG_IDS:
            if leg in row["cells"]:
                cells[leg] = row["cells"][leg]
            elif legs[leg]["availability"] == "unavailable":
                cells[leg] = _cell(reason="leg unavailable")
            elif leg == "bye":
                cells[leg] = _bye_cell(byes, team, args.week)
            else:
                cells[leg] = _cell(reason="not in input")
        out_rows.append({"player_key": key, "identity": identity, "legs": cells})

    if byes is not None and out_rows:
        bye_missing = sum(1 for r in out_rows if r["legs"]["bye"]["value"] is None)
        if bye_missing:
            legs["bye"]["availability"] = "partial"
    return {
        "schema": SCHEMA,
        "season": args.season,
        "content_week": args.week,
        "horizon": "week",
        "generated_at": _stamp(as_of),
        "producer": PRODUCER,
        "legs": legs,
        "rows": out_rows,
        "input_report": report,
    }


def _bye_cell(byes, team, week):
    if not team:
        return _cell(reason="no team")
    bye_week = byes.get(str(team).upper())
    if bye_week is None:
        return _cell(reason=f"team {team} not in bye table")
    return _cell({"team": str(team).upper(), "bye_week": bye_week, "on_bye": bye_week == week},
                 provenance="complete")


# ---------------------------------------------------------------- validate / write

def validate(doc: dict) -> list[str]:
    """The S1 contract validator when it is on this branch (JEG-1227), else
    the minimal structural check below. Returns error strings."""
    try:
        import weekly_inputs_contract  # noqa: PLC0415
    except ImportError:
        return _basic_check(doc)
    errors = []
    for issue in weekly_inputs_contract.validate(doc):
        if getattr(issue, "severity", "error") != "error":
            continue
        errors.append(str(getattr(issue, "code", "")) + ": " + str(getattr(issue, "message", issue)))
    return errors


def _basic_check(doc: dict) -> list[str]:
    errs = []
    if doc.get("schema") != SCHEMA or doc.get("horizon") != "week":
        errs.append("schema/horizon")
    for leg, m in doc["legs"].items():
        if m["availability"] == "unavailable":
            if m["freshness"] is not None or not m["unavailable_reason"]:
                errs.append(f"{leg}: unavailable leg needs freshness null and a reason")
        elif m["freshness"] not in ("current", "one_week_behind", "stale", "unknown"):
            errs.append(f"{leg}: freshness {m['freshness']!r}")
    for r in doc["rows"]:
        for leg, c in r["legs"].items():
            if (c["value"] is None) == (c["missing_reason"] is None):
                errs.append(f"{r['player_key']}/{leg}: value and missing_reason")
    return errs


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--as-of", required=True, help="ISO timestamp with zone; the only clock")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--espn-weekly", type=Path)
    p.add_argument("--status", type=Path)
    p.add_argument("--byes", type=Path)
    p.add_argument("--players", type=Path)
    p.add_argument("--sleeper-base", type=Path)
    args = p.parse_args(argv)
    if not 1 <= args.week <= 18:
        print(f"week {args.week} is outside the regular season", file=sys.stderr)
        return 2
    try:
        doc = build(args)
    except (InputError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    errors = validate(doc)
    if errors:
        for e in errors[:20]:
            print(f"invalid: {e}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(render(doc))
    os.replace(tmp, args.out)
    summary = {leg: m["availability"] for leg, m in doc["legs"].items()}
    print(f"wrote {args.out}: {len(doc['rows'])} rows; legs {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
