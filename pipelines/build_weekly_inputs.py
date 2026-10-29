#!/usr/bin/env python3
"""Offline weekly-input producer (JEG-1228, slice S2 of JEG-1195).

Turns explicit stored weekly inputs into the `weekly-inputs` v1 artifact
defined by JEG-1227 (`pipelines/lib/weekly_inputs_contract.py`,
`docs/weekly-inputs-contract.md`):

  experts.espn_weekly  ESPN weekly projections CSV (the shape of
                       data/inputs/espn_weekly_projections_2026.csv)
  status               an export of public.player_status_history rows (JSON list)
  bye                  the bye table (the shape of data/inputs/nfl_byes_2026.json)
  experts.ecr_weekly   no producer yet (S3b): always declared unavailable here
  vegas                no producer yet (S3): always declared unavailable here

Offline only: every input is a local path given on the command line, the
output path is explicit, and nothing reads the network, Supabase or the wall
clock (`--as-of` is the clock). Same inputs give the same bytes. Identity
aliases come from a local file (`--aliases`, default the committed
data/inputs/player_aliases.json), pinned by the producer itself, so Supabase
credentials in the environment never reach player_aliases' table read (JEG-1245).

Fails closed: the JEG-1227 contract validator must import and run. If it
cannot, the run is refused before any input is read and nothing is written;
there is no structural stand-in (JEG-1245).

Rules it keeps (docs/pipeline-rules.md §4-5, Jeremy 2026-10-29):
  - Weekly only. A rest-of-season input is refused and nothing is written
    ("do not blend weekly data with ROS data, ever").
  - Missing stays null with a reason; 0.0 is a value, never "missing".
  - Partial rows stay in, marked partial. Unresolved players stay in with
    player_key null and the reason, never guessed.
  - Availability (is there data) and freshness (the content week of the
    newest capture) are separate. Freshness is content vintage, never pull time.
  - Only the target season and week are used; rows for another week, another
    season, a later content week or after --as-of are counted in input_report
    and left out, never substituted.

Usage:
  python3 pipelines/build_weekly_inputs.py --season 2026 --week 8 \\
      --as-of 2026-10-29T02:00:00Z --out /tmp/inputs-wk8.json \\
      --players data/inputs/players_identity_snapshot.json \\
      [--espn-weekly FILE.csv] [--status FILE.json] [--byes FILE.json] \\
      [--sleeper-base FILE.json] [--aliases FILE.json]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import os
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
from nfl_week import NEW_YORK, SEASON as CALENDAR_SEASON, content_week_or_none  # noqa: E402
from timestamps import parse_iso_timestamp  # noqa: E402
import player_aliases  # noqa: E402 -- no read at import

SCHEMA = "weekly-inputs"
CONTRACT_MODULE = "weekly_inputs_contract"  # JEG-1227, pipelines/lib/
ALIAS_FILE = Path(player_aliases.ALIAS_FILE)  # the one shared list; read locally only
SCHEMA_VERSION = "1.0.0"
PRODUCER = "pipelines/build_weekly_inputs.py"
# CSV column -> contract scoring key (pipelines/lib/scoring.py keys).
ESPN_SCORING = {"std": "standard", "half_ppr": "half_ppr", "ppr": "ppr"}
SCORINGS = tuple(ESPN_SCORING.values())
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
LEG_IDS = ("bye", "experts.ecr_weekly", "experts.espn_weekly", "status", "vegas")
# The Sleeper fields public.player_status_history stores, unchanged
# (pipelines/save_player_status_history.py FIELDS).
STATUS_FIELDS = ("status", "injury_status", "injury_body_part", "injury_start_date",
                 "practice_participation", "depth_chart_position", "depth_chart_order")
ESPN_REQUIRED = ("season", "week", "player_key", "std", "half_ppr", "ppr", "snapshot_at")
# Column names only a rest-of-season file carries (the ESPN ROS CSV:
# ros_half_ppr, weeks_covered, season_block_half_ppr, r_* stat totals).
ROS_COLUMN_PREFIXES = ("ros", "r_", "weeks_covered", "season_block", "weeks_remaining")
NOT_IN_INPUT = "player not in this input"


class InputError(Exception):
    """An input this producer refuses outright; nothing is written."""


class ContractUnavailable(Exception):
    """The JEG-1227 validator cannot be imported or run; nothing is written."""


# ---------------------------------------------------------------- helpers

def _iso_utc(value: str) -> datetime:
    moment = parse_iso_timestamp(str(value).strip())
    if moment.tzinfo is None:
        raise ValueError(f"timestamp without a zone: {value!r}")
    return moment.astimezone(timezone.utc)


def _stamp(moment: datetime | None) -> str | None:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if moment else None


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
    """The vocabulary and rule of pipelines/check_reference_freshness.py."""
    if vintage_week is None:
        return "unknown"
    behind = max(target_week - vintage_week, 0)
    return "current" if behind == 0 else ("one_week_behind" if behind == 1 else "stale")


def _leg_meta(kind, source, units, scoring, reason, inputs=()):
    meta = {"kind": kind, "source": source, "horizon": "week", "units": units,
            "scoring": list(scoring) if scoring else None, "content_season": None,
            "content_week": None, "content_vintage": None, "captured_at": None,
            "availability": "unavailable", "freshness": None, "label": "unavailable",
            "missing_reason": reason}
    if inputs:
        meta["inputs"] = list(inputs)
    return meta


def _mark_available(meta, season, target_week, vintage_day: date | None, captured_at):
    """Content week of the newest capture (nfl_week, Tuesday flip) sets freshness."""
    vweek = content_week_or_none(vintage_day) if vintage_day else None
    meta.pop("missing_reason", None)
    meta.update(content_season=season, content_week=vweek,
                content_vintage=vintage_day.isoformat() if vintage_day else None,
                captured_at=captured_at, availability="complete",
                freshness=_freshness(target_week, vweek))
    meta["label"] = "stale" if meta["freshness"] == "stale" else "published"
    if vweek is None or captured_at is None:
        # The contract (JEG-1267) only lets a leg claim an age or "published"
        # when its input stamps both the vintage and the capture time. Missing
        # either, the age is unknown; nothing is filled in to make it look known.
        meta.update(content_week=None, freshness="unknown", label="modeled",
                    note="the input does not stamp both a content date and a capture time")


def _cell(values: dict, reason: str | None = None, reasons: dict | None = None):
    """A row leg: every null value gets a reason; provenance follows the nulls."""
    reasons = dict(reasons or {})
    out = {"values": dict(values)}
    nulls = [k for k, v in values.items() if v is None]
    for k in nulls:
        reasons.setdefault(k, reason or "not set in the source")
    present = len(values) - len(nulls)
    out["provenance"] = "missing" if present == 0 else ("complete" if not nulls else "partial")
    if nulls:
        out["missing_reason"] = {k: reasons[k] for k in nulls}
    return out


def _null_values(keys):
    return {k: None for k in keys}


@contextmanager
def _local_aliases(path: Path):
    """player_aliases.load() answers from `path` only while the registry is built.

    canonical_players.Registry reads the alias list through player_aliases.load(),
    which goes to Supabase whenever SUPABASE_URL and a key are set (and only logs
    a failed request). The producer pins the default load to the local file
    itself, so no request is ever attempted, whatever the environment holds.
    """
    pinned = player_aliases.load(str(path))  # a path read never touches Supabase
    real = player_aliases.load
    player_aliases.load = lambda p=None: pinned if p is None else real(p)
    try:
        yield
    finally:
        player_aliases.load = real


class Identity:
    """Canonical keys through the existing helpers (pipelines/lib/player_key_index.py)."""

    def __init__(self, players_path: Path, sleeper_base_path: Path | None,
                 aliases_path: Path = ALIAS_FILE):
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
        with _local_aliases(aliases_path):
            self.index = PlayerIndex(norm, base)
        self.known = self.index.by_key
        self.aliases = _file_meta(aliases_path)

    def check_key(self, key: int):
        """-> (key, None) or (None, reason)."""
        if key in self.known:
            return key, None
        return None, f"player_key {key} not in players snapshot"

    def resolve_sleeper(self, sleeper_id, name, pos):
        e, how = self.index.resolve_sleeper(sleeper_id, name or "", (pos or "").upper())
        return (e["player_key"], "player_index:" + how) if e else (None, f"unresolved: {how}")

    def entry(self, key):
        return self.known.get(key) or {}


# ---------------------------------------------------------------- readers

def _reject_ros_header(path: Path, header: list[str]):
    for col in header:
        low = col.strip().lower()
        if low.startswith(ROS_COLUMN_PREFIXES) or "_ros" in low:
            raise InputError(f"{path.name}: column {col!r} is rest-of-season; "
                             "weekly inputs never take ROS data")


def read_espn(path: Path, season: int, week: int, as_of: datetime, ident: Identity, report):
    meta = _leg_meta("expert", "espn", "fantasy_points", SCORINGS,
                     f"no ESPN weekly rows for season {season} week {week} on or before --as-of",
                     [_file_meta(path)])
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
        if (content_week_or_none(_ny_day(snap)) or 0) > week:
            report["later_content_week"] += 1
            continue
        key = _int(r["player_key"])
        ident_key = ("key", key) if key is not None else ("espn_row", str(line))
        candidates.setdefault(ident_key, []).append((snap, line, r))
    if not candidates:
        return meta, {}
    rows, vintage = {}, None
    for ident_key, cands in candidates.items():
        cands.sort(key=lambda c: (c[0], c[1]))
        newest = cands[-1][0]
        top = [c for c in cands if c[0] == newest]
        report["duplicate"] += len(cands) - 1
        vintage = newest if vintage is None or newest > vintage else vintage
        values = [{ESPN_SCORING[col]: _num(c[2][col]) for col in ESPN_SCORING} for c in top]
        r = top[-1][2]
        info = {"position": (r.get("pos") or "").upper() or None, "team": r.get("team") or None,
                "source_ids": {}, "resolved_by": None, "unresolved_reason": None, "name": None}
        key = ident_key[1] if ident_key[0] == "key" else None
        if key is None:
            info["source_ids"]["espn_row"] = int(ident_key[1])
            info["unresolved_reason"] = "espn row has no player_key"
        else:
            info["source_ids"]["espn_player_key"] = key
            key, why = ident.check_key(key)
            info["resolved_by"] = "espn_weekly.player_key" if key is not None else None
            info["unresolved_reason"] = why
        if any(v != values[0] for v in values[1:]):
            report["conflict"] += 1
            cell = _cell(_null_values(SCORINGS), "conflicting duplicate rows at the same snapshot")
        else:
            cell = _cell(values[0], "blank in the ESPN weekly file")
        rows[_row_id(key, info)] = (key, info, cell)
    _mark_available(meta, season, week, _ny_day(vintage), _stamp(vintage))
    return meta, rows


def read_status(path: Path, season: int, week: int, as_of: datetime, ident: Identity, report):
    meta = _leg_meta("status", "sleeper", "status", None,
                     f"no status snapshot in or before week {week} on or before --as-of",
                     [_file_meta(path)])
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        data = data.get("rows") or []
    as_of_day = _ny_day(as_of)
    usable = []
    for r in data:
        report["read"] += 1
        if str(r.get("horizon") or "week").lower() != "week":
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
        if cw is None:  # before content week 1 of this season
            report["wrong_season"] += 1
            continue
        if cw > week:
            report["later_content_week"] += 1
            continue
        usable.append((day, r))
    if not usable:
        return meta, {}
    latest = max(d for d, _ in usable)
    report["older_snapshot"] += sum(1 for d, _ in usable if d != latest)
    by_sid: dict[str, list] = {}
    fetched = []
    for d, r in usable:
        if d != latest:
            continue
        by_sid.setdefault(str(r.get("sleeper_id") or ""), []).append(r)
        if r.get("fetched_at"):
            try:
                fetched.append(_iso_utc(r["fetched_at"]))
            except ValueError:
                pass
    rows = {}
    for sid in sorted(by_sid):
        group = by_sid[sid]
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
            cell = _cell(_null_values(STATUS_FIELDS), "conflicting duplicate status rows")
        else:
            # Sleeper leaves a field unset when there is nothing to report
            # (a healthy player has no injury_status).
            cell = _cell(values[0], "not set in the Sleeper record")
        rid = _row_id(key, info)
        if rid in rows:
            # Two Sleeper ids on one player_key: keep neither value.
            report["conflict"] += 1
            prev = rows[rid]
            prev[1]["source_ids"]["sleeper_id"] = ",".join(
                sorted({prev[1]["source_ids"]["sleeper_id"], sid}))
            rows[rid] = (key, prev[1], _cell(_null_values(STATUS_FIELDS),
                                             "two sleeper ids for one player_key"))
            continue
        rows[rid] = (key, info, cell)
    _mark_available(meta, season, week, latest, _stamp(max(fetched)) if fetched else None)
    return meta, rows


def read_byes(path: Path, season: int, week: int):
    meta = _leg_meta("bye", "nfl_byes", "bye_week", None,
                     f"bye table is not for season {season}", [_file_meta(path)])
    data = json.loads(path.read_text())
    if _int(data.get("season")) != season or not isinstance(data.get("byes"), dict):
        return meta, None
    byes = {str(t).upper(): _int(w) for t, w in data["byes"].items()}
    # A season table, valid for every week of its season, but its source stamps
    # no capture date or content week. The contract (JEG-1267) then wants
    # freshness unknown and a non-published label; no date is invented here.
    meta.pop("missing_reason")
    meta.update(content_season=season, availability="complete", freshness="unknown",
                label="modeled", note="season bye table; the source stamps no capture date or week")
    return meta, byes


def _row_id(key, info):
    if key is not None:
        return (0, f"{key:012d}")
    ids = info["source_ids"]
    return (1, "|".join(f"{k}={ids[k]}" for k in sorted(ids)))


# ---------------------------------------------------------------- build

def build(args) -> dict:
    as_of = _iso_utc(args.as_of)
    counts = ("read", "wrong_season", "wrong_week", "later_content_week", "after_as_of",
              "older_snapshot", "duplicate", "conflict", "bad_row")
    report = {leg: {k: 0 for k in counts} for leg in ("experts.espn_weekly", "status")}
    report.update(unresolved_rows=0, position_out_of_scope=0)
    ident = Identity(args.players, args.sleeper_base, args.aliases)
    report["identity"] = {"aliases": ident.aliases, "alias_source": "local_file"}
    legs = {
        "experts.espn_weekly": _leg_meta("expert", "espn", "fantasy_points", SCORINGS,
                                         "input not supplied"),
        "experts.ecr_weekly": _leg_meta("expert", "fantasypros_ecr", "fantasy_points", SCORINGS,
                                        "no weekly ECR producer yet (JEG-1195 slice S3b)"),
        "vegas": _leg_meta("vegas", "propline", "fantasy_points", SCORINGS,
                           "no Vegas producer yet (JEG-1195 slice S3)"),
        "status": _leg_meta("status", "sleeper", "status", None, "input not supplied"),
        "bye": _leg_meta("bye", "nfl_byes", "bye_week", None, "input not supplied"),
    }
    per_leg: dict[str, dict] = {}
    if args.espn_weekly:
        legs["experts.espn_weekly"], per_leg["experts.espn_weekly"] = read_espn(
            args.espn_weekly, args.season, args.week, as_of, ident, report["experts.espn_weekly"])
    if args.status:
        legs["status"], per_leg["status"] = read_status(
            args.status, args.season, args.week, as_of, ident, report["status"])
    byes = None
    if args.byes:
        legs["bye"], byes = read_byes(args.byes, args.season, args.week)

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
        canon = ident.entry(key) if key is not None else {}
        position = espn_i.get("position") or stat_i.get("position") or canon.get("position") or None
        if position not in POSITIONS:
            report["position_out_of_scope"] += 1
            continue
        team = espn_i.get("team") or stat_i.get("team")
        ids = {**stat_i.get("source_ids", {}), **espn_i.get("source_ids", {})}
        name = canon.get("full_name") or stat_i.get("name")
        if not name:
            # The contract needs a display string; an unresolved ESPN row has
            # no name in its source, so it says which source row it is.
            name = "Unresolved " + ", ".join(f"{k} {ids[k]}" for k in sorted(ids))
        out = {"player_key": key, "name": name, "position": position, "team": team,
               "resolved_by": espn_i.get("resolved_by") or stat_i.get("resolved_by"),
               "source_ids": ids}
        if key is None:
            report["unresolved_rows"] += 1
            reasons = [i["unresolved_reason"] for i in (espn_i, stat_i) if i.get("unresolved_reason")]
            out["unresolved_reason"] = "; ".join(reasons)
        cells = {}
        for leg in LEG_IDS:
            keys = _leg_keys(legs[leg])
            if leg in row["cells"]:
                cells[leg] = row["cells"][leg]
            elif legs[leg]["availability"] == "unavailable":
                cells[leg] = {"provenance": "missing", "values": _null_values(keys)}
            elif leg == "bye":
                cells[leg] = _bye_cell(byes, team)
            else:
                cells[leg] = _cell(_null_values(keys), NOT_IN_INPUT)
        out["legs"] = cells
        out_rows.append(out)
    out_rows.sort(key=lambda r: (0, r["player_key"], "") if r["player_key"] is not None
                  else (1, 0, r["name"]))

    for leg, meta in legs.items():
        if meta["availability"] == "unavailable":
            continue
        if leg in ("experts.espn_weekly", "bye"):
            gap = any(r["legs"][leg]["provenance"] != "complete" for r in out_rows)
        else:  # status: a field Sleeper leaves unset is not a gap in the leg
            gap = any(r["legs"][leg]["provenance"] == "missing" for r in out_rows)
        meta["availability"] = "partial" if gap else "complete"
    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "horizon": "week",
        "season": args.season,
        "content_week": args.week,
        "built_at": _stamp(as_of),
        "producer": PRODUCER,
        "legs": legs,
        "players": out_rows,
        "input_report": report,
    }


def _leg_keys(meta):
    if meta["units"] == "status":
        return STATUS_FIELDS
    if meta["units"] == "bye_week":
        return ("bye_week",)
    return tuple(meta["scoring"])


def _bye_cell(byes, team):
    if not team:
        return _cell({"bye_week": None}, "no team")
    bye_week = byes.get(str(team).upper())
    if bye_week is None:
        return _cell({"bye_week": None}, f"team {team} not in bye table")
    return _cell({"bye_week": bye_week})


# ---------------------------------------------------------------- validate / write

def _load_contract():
    """The JEG-1227 contract module, or ContractUnavailable. No stand-in."""
    try:
        mod = importlib.import_module(CONTRACT_MODULE)
    except Exception as e:  # noqa: BLE001 -- missing or broken: refuse either way
        raise ContractUnavailable(
            f"contract validator {CONTRACT_MODULE} cannot be imported "
            f"({type(e).__name__}: {e}); refusing to write an unvalidated artifact") from e
    missing = [a for a in ("validate", "errors") if not callable(getattr(mod, a, None))]
    if missing:
        raise ContractUnavailable(
            f"contract validator {CONTRACT_MODULE} has no {', '.join(missing)}(); "
            "refusing to write an unvalidated artifact")
    return mod


def validate(doc: dict) -> list[str]:
    """Errors from the JEG-1227 contract validator. Raises ContractUnavailable
    when it cannot be imported or crashes; never returns [] without it."""
    contract = _load_contract()
    try:
        return [str(i) for i in contract.errors(contract.validate(doc))]
    except Exception as e:  # noqa: BLE001 -- a crashing validator validates nothing
        raise ContractUnavailable(
            f"contract validator {CONTRACT_MODULE} failed ({type(e).__name__}: {e}); "
            "refusing to write an unvalidated artifact") from e


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--week", type=int, required=True)
    p.add_argument("--as-of", required=True, help="ISO timestamp with zone; the only clock")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--players", type=Path, required=True,
                   help="players snapshot (player_key, full_name, position, gsis_id/sleeper_id)")
    p.add_argument("--espn-weekly", type=Path)
    p.add_argument("--status", type=Path)
    p.add_argument("--byes", type=Path)
    p.add_argument("--sleeper-base", type=Path)
    p.add_argument("--aliases", type=Path, default=ALIAS_FILE,
                   help="local verified alias list (player-aliases-v1); never read from Supabase")
    args = p.parse_args(argv)
    if args.season != CALENDAR_SEASON:
        # pipelines/nfl_week.py defines one season's calendar; another
        # season's content weeks would be wrong, so refuse rather than guess.
        print(f"season {args.season}: nfl_week.py defines only {CALENDAR_SEASON}", file=sys.stderr)
        return 2
    if not 1 <= args.week <= 18:
        print(f"week {args.week} is outside the regular season", file=sys.stderr)
        return 2
    try:
        _load_contract()  # before any input is read: no validator, no run
    except ContractUnavailable as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3
    try:
        doc = build(args)
    except (InputError, ValueError) as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    try:
        errors = validate(doc)
    except ContractUnavailable as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3
    if errors:
        for e in errors[:20]:
            print(f"invalid: {e}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    tmp.write_text(render(doc))
    os.replace(tmp, args.out)
    summary = {leg: m["availability"] for leg, m in sorted(doc["legs"].items())}
    print(f"wrote {args.out}: {len(doc['players'])} players; legs {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
