#!/usr/bin/env python3
"""Weekly-input artifact contract, schema `weekly-inputs` v1 (JEG-1227, S1 of JEG-1195).

One producer (JEG-1228, S2 onward) writes `data/weekly/inputs-wk{N}.json`;
Versus Vegas and later weekly consumers only read it. This module is the one
definition of that file's shape and the one validator for it. Stdlib only, no
network, no credentials. Contract doc: docs/weekly-inputs-contract.md.

Rules it enforces (sources: PR #1083 packet section 5 and the JEG-1195
decisions):

* Weekly only. Jeremy, 2026-10-29: "do not blend weekly data with ROS data,
  ever". The artifact and every leg carry `horizon: "week"`; a rest-of-season
  leg id, source or field name is rejected (`ros.*` codes).
* Numeric `player_key` (pipelines/lib/player_key_index.py). An unresolved row
  keeps `player_key: null` plus `unresolved_reason`, never a guessed key.
* Missing is `null` plus a reason, never zero (docs/pipeline-rules.md section 4).
  A real zero is a number with no reason; a zero carrying a reason is a
  zero-fill and is rejected.
* Availability (does the leg have data) and freshness (how old its content is)
  are separate fields. Freshness uses the existing vocabulary of
  pipelines/check_reference_freshness.py (current / one_week_behind / stale /
  unknown) and the same rule: 0 weeks behind is current, 1 is one week behind,
  2 or more is stale.
* Units are fixed per leg. A rank leg holds whole-number ranks, a points leg
  holds fantasy points; nothing here converts one into the other.

Version policy: `schema_version` is semver. A reader accepts any 1.x.y. Adding
an optional field is a minor bump. A field this reader does not know is an
error when the document claims a minor this reader knows (a producer typo) and
a warning when the document is newer (additive compatibility). A new weekly
expert source is a new `experts.<name>` leg and needs no version bump.

Usage:
    python3 pipelines/lib/weekly_inputs_contract.py FILE [FILE ...]
    python3 pipelines/lib/weekly_inputs_contract.py --json FILE
Exit status 1 when any file has an error; warnings alone exit 0.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

SCHEMA_NAME = "weekly-inputs"
SCHEMA_VERSION = "1.0.0"
READER_MAJOR, READER_MINOR = 1, 0

HORIZON = "week"
# Same keys as pipelines/lib/scoring.py SCORING.
SCORINGS = ("standard", "half_ppr", "ppr")
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DST")
SEASON_RANGE = (2020, 2100)
WEEK_RANGE = (1, 18)

LEG_KINDS = ("vegas", "expert", "status", "bye")
AVAILABILITY = ("complete", "partial", "unavailable")
FRESHNESS = ("current", "one_week_behind", "stale", "unknown")
LABELS = ("published", "previous-season", "modeled", "stale", "unavailable")
# Units each leg kind may carry. No unit is ever converted into another here.
UNITS_BY_KIND = {
    "vegas": ("fantasy_points",),
    "expert": ("fantasy_points", "rank"),
    "status": ("status",),
    "bye": ("bye_week",),
}
SCORED_UNITS = ("fantasy_points", "rank")
# Field names follow the stored Sleeper status history (pipelines/save_player_status_history.py).
STATUS_FIELDS = ("status", "injury_status", "injury_body_part", "injury_start_date",
                 "practice_participation", "depth_chart_position", "depth_chart_order")
BYE_FIELDS = ("bye_week",)
# Provenance per row leg. td-filled is the archived Vegas value (a leg filled
# from the touchdown market) and is valid on the vegas leg only.
PROVENANCE = ("complete", "td-filled", "partial", "missing")

LEG_ID_RE = re.compile(r"^(vegas|status|bye|experts\.[a-z][a-z0-9_]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ROS_TOKEN_RE = re.compile(r"(^|[._\-])(ros|rest_of_season|restofseason)([._\-]|$)", re.I)

TOP_REQUIRED = ("schema", "schema_version", "horizon", "season", "content_week",
                "built_at", "producer", "legs", "players")
TOP_OPTIONAL = ("input_report",)
LEG_REQUIRED = ("kind", "source", "horizon", "units", "scoring", "content_season",
                "content_week", "content_vintage", "captured_at", "availability",
                "freshness", "label")
LEG_OPTIONAL = ("game_week", "missing_reason", "note", "inputs")
ROW_REQUIRED = ("player_key", "name", "position", "team", "legs")
ROW_OPTIONAL = ("unresolved_reason", "resolved_by", "source_ids")
ROW_LEG_REQUIRED = ("provenance", "values")
ROW_LEG_OPTIONAL = ("missing_reason",)

# Every code the validator can emit. docs/weekly-inputs-contract.md lists the
# same set; tests/test_weekly_inputs_contract.py pins the two together.
CODES = {
    "json.invalid": "The file is not parseable JSON.",
    "type.document": "The document is not a JSON object.",
    "field.missing": "A required field is absent.",
    "field.unknown": "A field this reader does not know (error at a known minor version, warning at a newer one).",
    "field.type": "A field has the wrong JSON type.",
    "schema.name": "`schema` is not \"weekly-inputs\".",
    "version.malformed": "`schema_version` is not MAJOR.MINOR.PATCH.",
    "version.unsupported_major": "`schema_version` major is not 1.",
    "season.range": "A season is outside the supported range.",
    "season.future": "A leg's content season is later than the artifact's season.",
    "week.range": "A week is outside 1..18.",
    "week.future": "A leg's content week is later than the artifact's content week.",
    "timestamp.format": "A date or timestamp is not ISO 8601 (timestamps need a UTC offset).",
    "ros.horizon": "A horizon other than \"week\" (rest-of-season data is never allowed).",
    "ros.leg": "A leg id or source names rest-of-season data.",
    "ros.field": "A field name anywhere in the document names rest-of-season data.",
    "leg.id": "A leg id is not vegas, status, bye or experts.<lower_snake_name>.",
    "leg.none": "The document declares no legs.",
    "leg.kind_mismatch": "A leg's kind does not match its id.",
    "leg.no_reason": "An unavailable leg has no missing_reason.",
    "leg.unavailable_has_values": "A row carries a value for a leg declared unavailable.",
    "availability.value": "availability is not complete, partial or unavailable.",
    "availability.inconsistent": "A points or rank leg is complete but a row has a null, or partial with no null in any row.",
    "freshness.value": "freshness is not current, one_week_behind, stale, unknown or null.",
    "freshness.inconsistent": "freshness disagrees with the leg's content week, or is set on an unavailable leg.",
    "label.value": "label is not published, previous-season, modeled, stale or unavailable.",
    "label.inconsistent": "label disagrees with availability, freshness or content season.",
    "units.incompatible": "A leg's units are not allowed for its kind.",
    "scoring.unknown": "A scoring format other than standard, half_ppr or ppr.",
    "scoring.mismatch": "A leg's scoring list does not fit its units, or a row's values do not match the leg's scoring list.",
    "player.key_type": "player_key is not a positive integer or null.",
    "player.duplicate_key": "Two rows share a player_key.",
    "player.unresolved_no_reason": "A row with player_key null has no unresolved_reason.",
    "player.position": "position is not QB, RB, WR, TE, K or DST.",
    "order.players": "Rows are not ordered by player_key, then unresolved rows by name.",
    "row.undeclared_leg": "A row carries a leg the document does not declare.",
    "row.leg_missing": "A row omits a declared leg (write it with null values and reasons instead).",
    "value.type": "A value has the wrong type for the leg's units (points must be finite numbers).",
    "value.range": "A rank, bye week or depth order is not a positive whole number in range.",
    "missing.no_reason": "A null value has no missing_reason entry.",
    "missing.zero_filled": "A value carries a missing_reason but is not null (a zero or other fill).",
    "missing.reason_unused": "A missing_reason names a key the row does not have.",
    "provenance.value": "provenance is not complete, td-filled, partial or missing.",
    "provenance.inconsistent": "provenance disagrees with which values are null.",
}


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str
    severity: str = "error"  # "error" or "warning"

    def __str__(self) -> str:
        return f"{self.severity.upper()} {self.code} {self.path}: {self.message}"


def errors(issues: list[Issue]) -> list[Issue]:
    return [i for i in issues if i.severity == "error"]


def is_valid(issues: list[Issue]) -> bool:
    return not errors(issues)


def parse_version(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    m = VERSION_RE.match(value)
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def leg_kind_for_id(leg_id: str) -> str:
    return "expert" if leg_id.startswith("experts.") else leg_id


def freshness_for_weeks(artifact_week: int, leg_week: int | None) -> str:
    """The check_reference_freshness rule: 0 behind current, 1 behind one_week_behind, else stale."""
    if leg_week is None:
        return "unknown"
    behind = artifact_week - leg_week
    if behind <= 0:
        return "current"
    return "one_week_behind" if behind == 1 else "stale"


class _Validator:
    def __init__(self) -> None:
        self.issues: list[Issue] = []
        self.unknown_severity = "error"
        self.null_counts: dict[str, int] = {}

    def add(self, code: str, path: str, message: str, severity: str = "error") -> None:
        assert code in CODES, code
        self.issues.append(Issue(code, path, message, severity))

    # -- helpers ---------------------------------------------------------
    def fields(self, obj: dict, path: str, required: tuple, optional: tuple) -> None:
        for key in required:
            if key not in obj:
                self.add("field.missing", f"{path}.{key}", f"required field '{key}' is absent")
        for key in obj:
            if key not in required and key not in optional:
                self.add("field.unknown", f"{path}.{key}", f"field '{key}' is not in schema v{SCHEMA_VERSION}",
                         self.unknown_severity)

    def is_int(self, v: Any) -> bool:
        return isinstance(v, int) and not isinstance(v, bool)

    def int_in(self, v: Any, lo: int, hi: int, path: str, code: str, nullable: bool = False) -> bool:
        if v is None and nullable:
            return True
        if not self.is_int(v):
            self.add("field.type", path, f"expected an integer{' or null' if nullable else ''}, got {v!r}")
            return False
        if not lo <= v <= hi:
            self.add(code, path, f"{v} is outside {lo}..{hi}")
            return False
        return True

    def string(self, v: Any, path: str, nullable: bool = False) -> bool:
        if v is None and nullable:
            return True
        if not isinstance(v, str) or not v.strip():
            self.add("field.type", path, f"expected a non-empty string{' or null' if nullable else ''}, got {v!r}")
            return False
        return True

    def timestamp(self, v: Any, path: str, date_only: bool = False) -> None:
        if v is None:
            return
        ok = False
        if isinstance(v, str):
            try:
                if date_only:
                    date.fromisoformat(v)
                    ok = len(v) == 10
                else:
                    ok = datetime.fromisoformat(v.replace("Z", "+00:00")).tzinfo is not None
            except ValueError:
                ok = False
        if not ok:
            want = "an ISO date (YYYY-MM-DD)" if date_only else "an ISO timestamp with a UTC offset"
            self.add("timestamp.format", path, f"expected {want} or null, got {v!r}")

    def scan_ros(self, obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and ROS_TOKEN_RE.search(k):
                    self.add("ros.field", f"{path}.{k}", f"field '{k}' names rest-of-season data")
                self.scan_ros(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                self.scan_ros(v, f"{path}[{i}]")

    # -- document --------------------------------------------------------
    def run(self, doc: Any) -> list[Issue]:
        if not isinstance(doc, dict):
            self.add("type.document", "$", "the document must be a JSON object")
            return self.issues

        if doc.get("schema") != SCHEMA_NAME:
            self.add("schema.name", "$.schema", f"expected '{SCHEMA_NAME}', got {doc.get('schema')!r}")
        version = parse_version(doc.get("schema_version"))
        if version is None:
            self.add("version.malformed", "$.schema_version",
                     f"expected MAJOR.MINOR.PATCH, got {doc.get('schema_version')!r}")
        elif version[0] != READER_MAJOR:
            self.add("version.unsupported_major", "$.schema_version",
                     f"this reader handles major {READER_MAJOR}, got {doc['schema_version']}")
            return self.issues
        elif version[1] > READER_MINOR:
            self.unknown_severity = "warning"

        self.fields(doc, "$", TOP_REQUIRED, TOP_OPTIONAL)
        if "horizon" in doc and doc["horizon"] != HORIZON:
            self.add("ros.horizon", "$.horizon", f"the artifact is weekly only, got horizon {doc['horizon']!r}")
        self.scan_ros({k: v for k, v in doc.items() if k not in ("legs", "players")}, "$")

        season_ok = self.int_in(doc.get("season"), *SEASON_RANGE, "$.season", "season.range") \
            if "season" in doc else False
        week_ok = self.int_in(doc.get("content_week"), *WEEK_RANGE, "$.content_week", "week.range") \
            if "content_week" in doc else False
        if "built_at" in doc:
            if self.string(doc["built_at"], "$.built_at"):
                self.timestamp(doc["built_at"], "$.built_at")
        if "producer" in doc:
            self.string(doc["producer"], "$.producer")
        if "input_report" in doc and not isinstance(doc["input_report"], dict):
            self.add("field.type", "$.input_report", "input_report is an object (the producer's read counts)")
        season = doc.get("season") if season_ok else None
        week = doc.get("content_week") if week_ok else None

        legs = doc.get("legs")
        declared: dict[str, dict] = {}
        if "legs" in doc:
            if not isinstance(legs, dict):
                self.add("field.type", "$.legs", "legs must be an object keyed by leg id")
            elif not legs:
                self.add("leg.none", "$.legs", "declare at least one leg")
            else:
                for leg_id in sorted(legs):
                    meta = self.leg(leg_id, legs[leg_id], season, week)
                    if meta is not None:
                        declared[leg_id] = meta

        players = doc.get("players")
        if "players" in doc:
            if not isinstance(players, list):
                self.add("field.type", "$.players", "players must be a list")
            else:
                self.players(players, declared, legs if isinstance(legs, dict) else {})
        return self.issues

    def leg(self, leg_id: Any, meta: Any, season: int | None, week: int | None) -> dict | None:
        path = f"$.legs.{leg_id}"
        if not isinstance(leg_id, str) or not LEG_ID_RE.match(leg_id):
            if isinstance(leg_id, str) and ROS_TOKEN_RE.search(leg_id):
                self.add("ros.leg", path, f"leg id '{leg_id}' names rest-of-season data")
            else:
                self.add("leg.id", path, f"'{leg_id}' is not vegas, status, bye or experts.<lower_snake_name>")
            return None
        if ROS_TOKEN_RE.search(leg_id):
            self.add("ros.leg", path, f"leg id '{leg_id}' names rest-of-season data")
            return None
        if not isinstance(meta, dict):
            self.add("field.type", path, "a leg must be an object")
            return None
        self.fields(meta, path, LEG_REQUIRED, LEG_OPTIONAL)
        self.scan_ros(meta, path)

        kind = meta.get("kind")
        if "kind" in meta and kind != leg_kind_for_id(leg_id):
            self.add("leg.kind_mismatch", f"{path}.kind",
                     f"leg '{leg_id}' must have kind '{leg_kind_for_id(leg_id)}', got {kind!r}")
        kind = leg_kind_for_id(leg_id)
        if "source" in meta and self.string(meta["source"], f"{path}.source") \
                and ROS_TOKEN_RE.search(meta["source"]):
            self.add("ros.leg", f"{path}.source", f"source '{meta['source']}' names rest-of-season data")
        if "horizon" in meta and meta["horizon"] != HORIZON:
            self.add("ros.horizon", f"{path}.horizon", f"legs are weekly only, got horizon {meta['horizon']!r}")

        units = meta.get("units")
        units_ok = units in UNITS_BY_KIND[kind]
        if "units" in meta and not units_ok:
            self.add("units.incompatible", f"{path}.units",
                     f"a {kind} leg carries {' or '.join(UNITS_BY_KIND[kind])}, got {units!r}")
        scoring = meta.get("scoring")
        if "scoring" in meta and units_ok:
            if units in SCORED_UNITS:
                if not isinstance(scoring, list) or not scoring:
                    self.add("scoring.mismatch", f"{path}.scoring",
                             f"a {units} leg lists the scoring formats it carries, got {scoring!r}")
                    scoring = None
                else:
                    bad = [s for s in scoring if s not in SCORINGS]
                    for s in bad:
                        self.add("scoring.unknown", f"{path}.scoring", f"unknown scoring format {s!r}")
                    if len(set(scoring)) != len(scoring):
                        self.add("scoring.mismatch", f"{path}.scoring", "scoring lists a format twice")
                    if bad:
                        scoring = None
            elif scoring is not None:
                self.add("scoring.mismatch", f"{path}.scoring", f"a {units} leg has no scoring formats; use null")

        availability = meta.get("availability")
        if "availability" in meta and availability not in AVAILABILITY:
            self.add("availability.value", f"{path}.availability", f"got {availability!r}")
            availability = None
        freshness = meta.get("freshness")
        if "freshness" in meta and freshness is not None and freshness not in FRESHNESS:
            self.add("freshness.value", f"{path}.freshness", f"got {freshness!r}")
            freshness = "invalid"
        label = meta.get("label")
        if "label" in meta and label not in LABELS:
            self.add("label.value", f"{path}.label", f"got {label!r}")
            label = "invalid"

        unavailable = availability == "unavailable"
        nullable = unavailable or freshness == "unknown"
        c_season = meta.get("content_season")
        c_week = meta.get("content_week")
        s_ok = "content_season" in meta and self.int_in(c_season, *SEASON_RANGE, f"{path}.content_season",
                                                        "season.range", nullable=True)
        w_ok = "content_week" in meta and self.int_in(c_week, *WEEK_RANGE, f"{path}.content_week",
                                                      "week.range", nullable=True)
        if "game_week" in meta:
            self.int_in(meta["game_week"], *WEEK_RANGE, f"{path}.game_week", "week.range", nullable=True)
        if "content_vintage" in meta:
            self.timestamp(meta["content_vintage"], f"{path}.content_vintage", date_only=True)
        if "captured_at" in meta:
            self.timestamp(meta["captured_at"], f"{path}.captured_at")
        if "inputs" in meta:
            self.inputs(meta["inputs"], f"{path}.inputs")

        if unavailable:
            if not isinstance(meta.get("missing_reason"), str) or not meta["missing_reason"].strip():
                self.add("leg.no_reason", f"{path}.missing_reason", "an unavailable leg says why")
            if freshness is not None:
                self.add("freshness.inconsistent", f"{path}.freshness",
                         "an unavailable leg has no content to age; freshness must be null")
            if label not in (None, "unavailable", "invalid"):
                self.add("label.inconsistent", f"{path}.label", "an unavailable leg is labelled unavailable")
        else:
            if "freshness" in meta and freshness is None:
                self.add("freshness.inconsistent", f"{path}.freshness",
                         "a leg with data has a freshness (use unknown when the week is unknown)")
            if label == "unavailable":
                self.add("label.inconsistent", f"{path}.label",
                         f"the leg is {availability}, so it cannot be labelled unavailable")
            if s_ok and season is not None and c_season is not None:
                if c_season > season:
                    self.add("season.future", f"{path}.content_season",
                             f"content season {c_season} is after the artifact season {season}")
                elif c_season < season and label not in ("previous-season", "invalid"):
                    self.add("label.inconsistent", f"{path}.label",
                             f"content season {c_season} is before {season}; label it previous-season")
                elif c_season == season and label == "previous-season":
                    self.add("label.inconsistent", f"{path}.label",
                             f"content season {c_season} is this season, not previous-season")
            same_season = s_ok and c_season is not None and c_season == season
            if w_ok and week is not None and same_season and freshness not in ("invalid", None):
                if c_week is not None and c_week > week:
                    self.add("week.future", f"{path}.content_week",
                             f"content week {c_week} is after the artifact week {week}")
                else:
                    expected = freshness_for_weeks(week, c_week)
                    if freshness != expected:
                        self.add("freshness.inconsistent", f"{path}.freshness",
                                 f"content week {c_week} against artifact week {week} is {expected}, "
                                 f"not {freshness}")
            if s_ok and c_season is not None and season is not None and c_season < season \
                    and freshness not in ("stale", "invalid"):
                self.add("freshness.inconsistent", f"{path}.freshness",
                         "a previous-season leg is stale")
            if freshness == "stale" and label == "published":
                self.add("label.inconsistent", f"{path}.label", "stale content is labelled stale, not published")

        return {"kind": kind, "units": units if units_ok else None,
                "scoring": scoring if units_ok and units in SCORED_UNITS else None,
                "unavailable": unavailable, "availability": availability}

    def inputs(self, inputs: Any, path: str) -> None:
        if not isinstance(inputs, list):
            self.add("field.type", path, "inputs is a list of {name, sha256}")
            return
        for i, item in enumerate(inputs):
            ipath = f"{path}[{i}]"
            if not isinstance(item, dict):
                self.add("field.type", ipath, "an input is an object with name and sha256")
                continue
            self.fields(item, ipath, ("name", "sha256"), ())
            if "name" in item:
                self.string(item["name"], f"{ipath}.name")
            if "sha256" in item and not (isinstance(item["sha256"], str) and SHA256_RE.match(item["sha256"])):
                self.add("field.type", f"{ipath}.sha256", "sha256 is 64 lowercase hex characters")

    def players(self, players: list, declared: dict[str, dict], legs: dict) -> None:
        seen: dict[int, int] = {}
        order: list[tuple] = []
        for i, row in enumerate(players):
            path = f"$.players[{i}]"
            if not isinstance(row, dict):
                self.add("field.type", path, "a player row must be an object")
                continue
            self.fields(row, path, ROW_REQUIRED, ROW_OPTIONAL)
            self.scan_ros({k: v for k, v in row.items() if k != "legs"}, path)
            key = row.get("player_key")
            if "player_key" in row:
                if key is None:
                    reason = row.get("unresolved_reason")
                    if not isinstance(reason, str) or not reason.strip():
                        self.add("player.unresolved_no_reason", f"{path}.unresolved_reason",
                                 "a row with player_key null says why it is unresolved")
                elif not self.is_int(key) or key <= 0:
                    self.add("player.key_type", f"{path}.player_key",
                             f"player_key is a positive integer or null, got {key!r}")
                    key = "invalid"
                elif key in seen:
                    self.add("player.duplicate_key", f"{path}.player_key",
                             f"player_key {key} is already on players[{seen[key]}]")
                else:
                    seen[key] = i
            if "name" in row:
                self.string(row["name"], f"{path}.name")
            if "position" in row and row["position"] not in POSITIONS:
                self.add("player.position", f"{path}.position", f"got {row['position']!r}")
            if "team" in row:
                self.string(row["team"], f"{path}.team", nullable=True)
            if "resolved_by" in row:
                self.string(row["resolved_by"], f"{path}.resolved_by", nullable=True)
            if "source_ids" in row and not isinstance(row["source_ids"], dict):
                self.add("field.type", f"{path}.source_ids", "source_ids is an object of source id names to ids")
            if key != "invalid" and isinstance(row.get("name"), str):
                order.append((i, key, row["name"]))

            row_legs = row.get("legs")
            if "legs" not in row:
                continue
            if not isinstance(row_legs, dict):
                self.add("field.type", f"{path}.legs", "legs must be an object keyed by leg id")
                continue
            for leg_id in row_legs:
                if leg_id not in legs:
                    if isinstance(leg_id, str) and ROS_TOKEN_RE.search(leg_id):
                        self.add("ros.leg", f"{path}.legs.{leg_id}", f"leg '{leg_id}' names rest-of-season data")
                    else:
                        self.add("row.undeclared_leg", f"{path}.legs.{leg_id}",
                                 f"leg '{leg_id}' is not declared in $.legs")
            for leg_id in sorted(declared):
                if leg_id not in row_legs:
                    self.add("row.leg_missing", f"{path}.legs.{leg_id}",
                             "write the leg with null values and a missing_reason instead of omitting it")
                else:
                    self.row_leg(row_legs[leg_id], declared[leg_id], f"{path}.legs.{leg_id}", leg_id)

        for leg_id in sorted(declared):
            meta = declared[leg_id]
            if meta["units"] not in SCORED_UNITS or meta["unavailable"] or leg_id not in self.null_counts:
                continue
            nulls = self.null_counts[leg_id]
            if meta["availability"] == "complete" and nulls:
                self.add("availability.inconsistent", f"$.legs.{leg_id}.availability",
                         f"{nulls} null values in rows; a leg with missing rows is partial")
            elif meta["availability"] == "partial" and not nulls:
                self.add("availability.inconsistent", f"$.legs.{leg_id}.availability",
                         "every row is complete; the leg is complete, not partial")

        def sort_key(t: tuple) -> tuple:
            _, k, name = t
            return (0, k, "") if isinstance(k, int) else (1, 0, name)
        if [t[0] for t in order] != [t[0] for t in sorted(order, key=sort_key)]:
            self.add("order.players", "$.players",
                     "order rows by player_key ascending, then unresolved rows by name")

    def row_leg(self, cell: Any, meta: dict, path: str, leg_id: str) -> None:
        if not isinstance(cell, dict):
            self.add("field.type", path, "a row leg must be an object with provenance and values")
            return
        self.fields(cell, path, ROW_LEG_REQUIRED, ROW_LEG_OPTIONAL)
        self.scan_ros(cell, path)
        values = cell.get("values")
        reasons = cell.get("missing_reason") or {}
        if not isinstance(reasons, dict):
            self.add("field.type", f"{path}.missing_reason", "missing_reason is an object keyed like values")
            reasons = {}
        if not isinstance(values, dict):
            if "values" in cell:
                self.add("field.type", f"{path}.values", "values must be an object")
            return

        units = meta["units"]
        if units in SCORED_UNITS:
            expected_keys = meta["scoring"]
        elif units == "status":
            expected_keys = list(STATUS_FIELDS)
        elif units == "bye_week":
            expected_keys = list(BYE_FIELDS)
        else:
            expected_keys = None
        if expected_keys is not None:
            scored = units in SCORED_UNITS
            for k in values:
                if k in expected_keys:
                    continue
                vpath = f"{path}.values.{k}"
                if not scored:
                    self.add("field.unknown", vpath, f"'{k}' is not a {units} field", self.unknown_severity)
                elif k not in SCORINGS:
                    self.add("scoring.unknown", vpath, f"unknown scoring format '{k}'")
                else:
                    self.add("scoring.mismatch", vpath, f"'{k}' is not in the leg's scoring {expected_keys}")
            for k in expected_keys:
                if k not in values:
                    self.add("scoring.mismatch" if scored else "field.missing", f"{path}.values.{k}",
                             f"'{k}' is absent; write null with a missing_reason")

        present = 0
        nulls = 0
        self.null_counts.setdefault(leg_id, 0)
        for k, v in values.items():
            vpath = f"{path}.values.{k}"
            if v is None:
                nulls += 1
                self.null_counts[leg_id] = self.null_counts.get(leg_id, 0) + 1
                r = reasons.get(k)
                if not meta["unavailable"] and (not isinstance(r, str) or not r.strip()):
                    self.add("missing.no_reason", f"{path}.missing_reason.{k}", f"'{k}' is null with no reason")
                continue
            present += 1
            if meta["unavailable"]:
                self.add("leg.unavailable_has_values", vpath,
                         f"leg '{leg_id}' is declared unavailable, so every value is null (got {v!r})")
                continue
            if k in reasons:
                self.add("missing.zero_filled", vpath,
                         f"'{k}' has a missing_reason but holds {v!r}; a missing value stays null")
            self.value(v, units, k, vpath)
        for k in reasons:
            if k not in values:
                self.add("missing.reason_unused", f"{path}.missing_reason.{k}", f"no value '{k}' to explain")

        prov = cell.get("provenance")
        if "provenance" not in cell:
            return
        if prov not in PROVENANCE:
            self.add("provenance.value", f"{path}.provenance", f"got {prov!r}")
            return
        if meta["unavailable"]:
            if prov != "missing":
                self.add("provenance.inconsistent", f"{path}.provenance", "an unavailable leg's rows are missing")
            return
        if prov == "td-filled" and meta["kind"] != "vegas":
            self.add("provenance.inconsistent", f"{path}.provenance", "td-filled applies to the vegas leg only")
        expected = "missing" if present == 0 else ("complete" if nulls == 0 else "partial")
        ok = prov == expected or (prov == "td-filled" and present > 0)
        if not ok:
            self.add("provenance.inconsistent", f"{path}.provenance",
                     f"{present} values and {nulls} nulls is {expected}, not {prov}")

    def value(self, v: Any, units: str, key: str, path: str) -> None:
        if units == "fantasy_points":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                self.add("value.type", path, f"fantasy points are a finite number or null, got {v!r}")
        elif units == "rank":
            if not self.is_int(v):
                self.add("value.type", path, f"a rank is a whole number or null, got {v!r}")
            elif v < 1:
                self.add("value.range", path, f"a rank starts at 1, got {v}")
        elif units == "bye_week":
            if not self.is_int(v):
                self.add("value.type", path, f"a bye week is a whole number or null, got {v!r}")
            elif not WEEK_RANGE[0] <= v <= WEEK_RANGE[1]:
                self.add("value.range", path, f"a bye week is in 1..18, got {v}")
        elif units == "status":
            if key == "depth_chart_order":
                if not self.is_int(v):
                    self.add("value.type", path, f"depth_chart_order is a whole number or null, got {v!r}")
                elif v < 1:
                    self.add("value.range", path, f"depth_chart_order starts at 1, got {v}")
            elif key == "injury_start_date":
                self.timestamp(v, path, date_only=True)
            elif not isinstance(v, str) or not v.strip():
                self.add("value.type", path, f"'{key}' is a non-empty string or null, got {v!r}")


def validate(doc: Any) -> list[Issue]:
    """Every error and warning for one parsed weekly-input document, in a stable order."""
    return _Validator().run(doc)


def validate_text(text: str) -> list[Issue]:
    try:
        doc = json.loads(text)
    except ValueError as exc:
        return [Issue("json.invalid", "$", str(exc))]
    return validate(doc)


def validate_file(path: str | Path) -> list[Issue]:
    return validate_text(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate weekly-input artifacts (schema weekly-inputs v1).")
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true", help="print issues as JSON")
    args = ap.parse_args(argv)
    failed = False
    report = {}
    for f in args.files:
        issues = validate_file(f)
        failed = failed or not is_valid(issues)
        report[f] = [asdict(i) for i in issues]
        if not args.json:
            print(f"{f}: {'OK' if is_valid(issues) else 'INVALID'} "
                  f"({len(errors(issues))} errors, {len(issues) - len(errors(issues))} warnings)")
            for i in issues:
                print(f"  {i}")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
