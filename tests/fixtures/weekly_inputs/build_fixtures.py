#!/usr/bin/env python3
"""Build tests/fixtures/weekly_inputs/ (JEG-1227): weekly-input contract cases.

Synthetic data only: the players, keys and numbers are made up and price
nothing. Each case is a small mutation of one base document, so a reader can
see exactly what makes a case valid or invalid. `expected.json` lists, for
every case, the error codes (and warning codes) the validator must report.

tests/test_weekly_inputs_contract.py rebuilds every case in memory and requires
the committed files to match byte for byte, so the fixtures never drift from
this script. To add a case: add it here, run the script, commit both.

Run: python3 tests/fixtures/weekly_inputs/build_fixtures.py
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent

UNAVAILABLE_LEG = {
    "units": None, "scoring": None, "content_season": None, "content_week": None,
    "content_vintage": None, "captured_at": None, "availability": "unavailable",
    "freshness": None, "label": "unavailable",
}


def base() -> dict:
    """A complete, current week-8 artifact: one weekly expert leg, status and byes."""
    return {
        "schema": "weekly-inputs",
        "schema_version": "1.0.0",
        "horizon": "week",
        "season": 2026,
        "content_week": 8,
        "built_at": "2026-10-28T13:30:00Z",
        "producer": "tests/fixtures/weekly_inputs/build_fixtures.py",
        "input_report": {"experts.espn_weekly": {"read": 4, "duplicate": 0}, "unresolved_rows": 0},
        "legs": {
            "bye": {
                "kind": "bye", "source": "nfl_byes_2026", "horizon": "week", "units": "bye_week",
                "scoring": None, "content_season": 2026, "content_week": 8,
                "content_vintage": "2026-09-01", "captured_at": "2026-09-01T12:00:00Z",
                "availability": "complete", "freshness": "current", "label": "published",
            },
            "experts.espn_weekly": {
                "kind": "expert", "source": "espn", "horizon": "week", "units": "fantasy_points",
                "scoring": ["standard", "half_ppr", "ppr"], "content_season": 2026,
                "content_week": 8, "content_vintage": "2026-10-28",
                "captured_at": "2026-10-28T12:40:00Z", "availability": "complete",
                "freshness": "current", "label": "published",
            },
            "status": {
                "kind": "status", "source": "sleeper", "horizon": "week", "units": "status",
                "scoring": None, "content_season": 2026, "content_week": 8,
                "content_vintage": "2026-10-28", "captured_at": "2026-10-28T13:10:00Z",
                "availability": "complete", "freshness": "current", "label": "published",
                "inputs": [{"name": "player_status_history.json", "sha256": "0" * 64}],
            },
        },
        "players": [
            _row(9000101, "Fixture Quarterback", "QB", "AAA", (18.4, 18.4, 18.4), 1, ("Active", None, "Full", 1)),
            _row(9000102, "Fixture Running Back", "RB", "BBB", (12.1, 13.6, 15.1), 11, ("Active", None, "Full", 1)),
            _row(9000103, "Fixture Wide Receiver", "WR", "CCC", (9.8, 12.3, 14.8), 7, ("Active", "Questionable", "Limited", 2)),
            _row(9000104, "Fixture Tight End", "TE", "DDD", (5.2, 6.9, 8.6), 9, ("Active", None, "Full", 1)),
        ],
    }


def _row(key, name, pos, team, pts, bye, status) -> dict:
    s, inj, prac, depth = status
    status_values = {"status": s, "injury_status": inj, "injury_body_part": "Hamstring" if inj else None,
                     "injury_start_date": "2026-10-26" if inj else None, "practice_participation": prac,
                     "depth_chart_position": pos, "depth_chart_order": depth}
    status_reasons = {k: "no designation this week" for k, v in status_values.items() if v is None}
    status_cell = {"provenance": "partial" if status_reasons else "complete", "values": status_values}
    if status_reasons:
        status_cell["missing_reason"] = status_reasons
    return {
        "player_key": key, "name": name, "position": pos, "team": team,
        "resolved_by": "espn_player_id", "source_ids": {"espn_player_id": key - 9000000, "sleeper_id": f"S{key}"},
        "legs": {
            "bye": {"provenance": "complete", "values": {"bye_week": bye}},
            "experts.espn_weekly": {
                "provenance": "complete",
                "values": dict(zip(("standard", "half_ppr", "ppr"), pts)),
            },
            "status": status_cell,
        },
    }


def add_leg(doc: dict, leg_id: str, meta: dict, cells: list[dict]) -> None:
    doc["legs"][leg_id] = meta
    for row, cell in zip(doc["players"], cells):
        row["legs"][leg_id] = cell


def unavailable_leg(doc: dict, leg_id: str, kind: str, source: str, reason: str, keys: list[str]) -> None:
    meta = {"kind": kind, "source": source, "horizon": "week", **UNAVAILABLE_LEG,
            "missing_reason": reason}
    meta["units"] = "rank" if leg_id == "experts.ecr_weekly" else "fantasy_points"
    meta["scoring"] = keys
    add_leg(doc, leg_id, meta,
            [{"provenance": "missing", "values": {k: None for k in keys}} for _ in doc["players"]])


def espn(doc: dict) -> dict:
    return doc["legs"]["experts.espn_weekly"]


def cell(doc: dict, i: int, leg: str = "experts.espn_weekly") -> dict:
    return doc["players"][i]["legs"][leg]


# -- valid cases -----------------------------------------------------------

def v_complete(d):
    return d


def v_partial(d):
    espn(d)["availability"] = "partial"
    c = cell(d, 2)
    c["values"]["half_ppr"] = None
    c["provenance"] = "partial"
    c["missing_reason"] = {"half_ppr": "source row had no half-PPR projection"}
    return d


def v_stale(d):
    s = d["legs"]["status"]
    s.update(content_week=6, content_vintage="2026-10-13", captured_at="2026-10-13T13:10:00Z",
             freshness="stale", label="stale")
    return d


def v_one_week_behind(d):
    espn(d).update(content_week=7, content_vintage="2026-10-21", captured_at="2026-10-21T12:40:00Z",
                   freshness="one_week_behind")
    return d


def v_unknown(d):
    meta = {"kind": "expert", "source": "cbs", "horizon": "week", "units": "fantasy_points",
            "scoring": ["ppr"], "content_season": 2026, "content_week": None,
            "content_vintage": None, "captured_at": "2026-10-28T09:00:00Z",
            "availability": "complete", "freshness": "unknown", "label": "modeled",
            "note": "captured, week not stamped by the source"}
    add_leg(d, "experts.cbs_weekly", meta,
            [{"provenance": "complete", "values": {"ppr": p}} for p in (17.0, 14.4, 13.9, 8.1)])
    return d


def v_unknown_no_provenance(d):
    # Valid control for the null-provenance cases: nothing stamped, so freshness unknown and not published.
    v_unknown(d)
    d["legs"]["experts.cbs_weekly"].update(content_season=None, captured_at=None)
    return d


def v_unavailable(d):
    unavailable_leg(d, "experts.ecr_weekly", "expert", "fantasypros",
                    "no weekly ECR producer yet (S3b)", ["half_ppr"])
    unavailable_leg(d, "vegas", "vegas", "propline",
                    "PropLine feed on hold until the key exists (S3)", ["standard", "half_ppr", "ppr"])
    return d


def v_rank_leg(d):
    meta = {"kind": "expert", "source": "fantasypros", "horizon": "week", "units": "rank",
            "scoring": ["half_ppr"], "content_season": 2026, "content_week": 8,
            "content_vintage": "2026-10-28", "captured_at": "2026-10-28T14:00:00Z",
            "availability": "partial", "freshness": "current", "label": "published"}
    cells = [{"provenance": "complete", "values": {"half_ppr": r}} for r in (3, 14, 22)]
    cells.append({"provenance": "missing", "values": {"half_ppr": None},
                  "missing_reason": {"half_ppr": "not ranked this week"}})
    add_leg(d, "experts.ecr_weekly", meta, cells)
    return d


def v_zero_value(d):
    cell(d, 3)["values"]["standard"] = 0.0
    return d


def v_unresolved_player(d):
    row = copy.deepcopy(d["players"][1])
    row.update(player_key=None, name="Fixture Unmatched Back", team="EEE", resolved_by=None,
               source_ids={"espn_player_id": 999}, unresolved_reason="no player_key match for name and position")
    d["players"].append(row)
    return d


def v_previous_season(d):
    meta = {"kind": "expert", "source": "usage_trends", "horizon": "week", "units": "fantasy_points",
            "scoring": ["ppr"], "content_season": 2025, "content_week": 8,
            "content_vintage": "2025-10-28", "captured_at": "2025-10-28T12:00:00Z",
            "availability": "complete", "freshness": "stale", "label": "previous-season"}
    add_leg(d, "experts.usage_2025", meta,
            [{"provenance": "complete", "values": {"ppr": p}} for p in (16.2, 11.0, 12.7, 7.4)])
    return d


def v_additive_minor(d):
    d["schema_version"] = "1.1.0"
    d["build_notes"] = "a field added in a later minor version"
    espn(d)["sample_size"] = 4
    return d


VALID: dict[str, Callable] = {
    "complete": v_complete, "partial": v_partial, "stale": v_stale,
    "one_week_behind": v_one_week_behind, "unknown": v_unknown,
    "unknown_no_provenance": v_unknown_no_provenance, "unavailable": v_unavailable,
    "rank_leg": v_rank_leg, "zero_value": v_zero_value, "unresolved_player": v_unresolved_player,
    "previous_season": v_previous_season, "additive_minor": v_additive_minor,
}
VALID_WARNINGS = {"additive_minor": ["field.unknown", "field.unknown"]}


# -- invalid cases ---------------------------------------------------------
# name -> (mutation, expected error codes in validator order)

def _set(path_fn, value):
    def mutate(d):
        obj, key = path_fn(d)
        obj[key] = value
        return d
    return mutate


def _zero_filled(d):
    c = cell(d, 2)
    c["values"]["half_ppr"] = 0.0
    c["missing_reason"] = {"half_ppr": "no projection"}
    return d


INVALID: dict[str, tuple[Callable, list[str]]] = {
    "zero_filled": (lambda d: _zero_filled(d), ["missing.zero_filled"]),
    "null_no_reason": (lambda d: (cell(d, 2)["values"].update(half_ppr=None),
                                  cell(d, 2).update(provenance="partial"),
                                  espn(d).update(availability="partial"), d)[-1],
                       ["missing.no_reason"]),
    "unavailable_has_values": (lambda d: (v_unavailable(d), cell(d, 0, "vegas")["values"].update(ppr=0.0), d)[-1],
                               ["leg.unavailable_has_values"]),
    "unavailable_no_reason": (lambda d: (v_unavailable(d), d["legs"]["vegas"].pop("missing_reason"), d)[-1],
                              ["leg.no_reason"]),
    "unavailable_with_freshness": (lambda d: (v_unavailable(d), d["legs"]["vegas"].update(freshness="current"),
                                              d)[-1],
                                   ["freshness.inconsistent"]),
    "duplicate_key": (_set(lambda d: (d["players"][1], "player_key"), 9000101), ["player.duplicate_key"]),
    "unresolved_no_reason": (lambda d: (v_unresolved_player(d), d["players"][-1].pop("unresolved_reason"), d)[-1],
                             ["player.unresolved_no_reason"]),
    "key_as_string": (_set(lambda d: (d["players"][0], "player_key"), "9000101"), ["player.key_type"]),
    "wrong_week_current": (lambda d: (espn(d).update(content_week=7), d)[-1], ["freshness.inconsistent"]),
    "future_week": (lambda d: (espn(d).update(content_week=9), d)[-1], ["week.future"]),
    "future_season": (lambda d: (espn(d).update(content_season=2027), d)[-1], ["season.future"]),
    "last_season_as_current": (lambda d: (d.update(season=2027), d)[-1],
                               ["label.inconsistent", "freshness.inconsistent"] * 3),
    "stale_labelled_published": (lambda d: (v_stale(d), d["legs"]["status"].update(label="published"), d)[-1],
                                 ["label.inconsistent"]),
    "complete_labelled_unavailable": (lambda d: (espn(d).update(label="unavailable"), d)[-1],
                                      ["label.inconsistent"]),
    "rank_as_points": (lambda d: (v_rank_leg(d), cell(d, 0, "experts.ecr_weekly")["values"].update(half_ppr=3.5),
                                  d)[-1],
                       ["value.type"]),
    "points_units_on_status": (lambda d: (d["legs"]["status"].update(units="fantasy_points"), d)[-1],
                               ["units.incompatible"]),
    "unknown_scoring": (lambda d: (cell(d, 0)["values"].update(full_ppr=18.4), d)[-1], ["scoring.unknown"]),
    "scoring_key_missing": (lambda d: (cell(d, 0)["values"].pop("ppr"), d)[-1], ["scoring.mismatch"]),
    "nan_points": (lambda d: (cell(d, 0)["values"].update(ppr=float("nan")), d)[-1], ["value.type"]),
    "provenance_mismatch": (lambda d: (cell(d, 2)["values"].update(half_ppr=None),
                                       cell(d, 2).update(missing_reason={"half_ppr": "no projection"}),
                                       espn(d).update(availability="partial"), d)[-1],
                            ["provenance.inconsistent"]),
    "complete_leg_with_null": (lambda d: (v_partial(d), espn(d).update(availability="complete"), d)[-1],
                               ["availability.inconsistent"]),
    "partial_leg_all_complete": (lambda d: (espn(d).update(availability="partial"), d)[-1],
                                 ["availability.inconsistent"]),
    "td_filled_on_expert": (lambda d: (cell(d, 0).update(provenance="td-filled"), d)[-1],
                            ["provenance.inconsistent"]),
    "ros_horizon": (lambda d: (d.update(horizon="ros"), d)[-1], ["ros.horizon"]),
    "ros_leg_horizon": (lambda d: (espn(d).update(horizon="season"), d)[-1], ["ros.horizon"]),
    "ros_leg_id": (lambda d: (d["legs"].update({"experts.espn_ros": d["legs"].pop("experts.espn_weekly")}),
                              [r["legs"].update({"experts.espn_ros": r["legs"].pop("experts.espn_weekly")})
                               for r in d["players"]], d)[-1],
                   ["ros.leg"]),
    "ros_field": (lambda d: (d["players"][0].update(ros_points=210.5), d)[-1],
                  ["field.unknown", "ros.field"]),
    "version_major": (lambda d: (d.update(schema_version="2.0.0"), d)[-1], ["version.unsupported_major"]),
    "version_malformed": (lambda d: (d.update(schema_version="v1"), d)[-1], ["version.malformed"]),
    "schema_name": (lambda d: (d.update(schema="weekly_inputs"), d)[-1], ["schema.name"]),
    "unknown_field_known_minor": (lambda d: (d.update(build_notes="typo-prone extra"), d)[-1], ["field.unknown"]),
    "missing_required": (lambda d: (d.pop("built_at"), d)[-1], ["field.missing"]),
    "undeclared_leg": (lambda d: (d["players"][0]["legs"].update(vegas={"provenance": "missing", "values": {}}),
                                  d)[-1],
                       ["row.undeclared_leg"]),
    "row_leg_missing": (lambda d: (d["players"][1]["legs"].pop("bye"), d)[-1], ["row.leg_missing"]),
    "kind_mismatch": (lambda d: (espn(d).update(kind="vegas"), d)[-1], ["leg.kind_mismatch"]),
    "bad_leg_id": (lambda d: (d["legs"].update({"Experts.ESPN": d["legs"].pop("experts.espn_weekly")}), d)[-1],
                   ["leg.id"] + ["row.undeclared_leg"] * 4),
    "out_of_order": (lambda d: (d["players"].reverse(), d)[-1], ["order.players"]),
    # Unknown provenance never passes as current or published (JEG-1267).
    "current_null_season": (lambda d: (espn(d).update(content_season=None), d)[-1], ["leg.provenance_unknown"]),
    "current_null_week": (lambda d: (espn(d).update(content_week=None), d)[-1],
                          ["leg.provenance_unknown", "freshness.inconsistent"]),
    "current_null_vintage": (lambda d: (espn(d).update(content_vintage=None), d)[-1], ["leg.provenance_unknown"]),
    "current_null_captured_at": (lambda d: (espn(d).update(captured_at=None), d)[-1], ["leg.provenance_unknown"]),
    "current_null_provenance": (lambda d: (espn(d).update(content_season=None, content_week=None,
                                                          content_vintage=None, captured_at=None), d)[-1],
                                ["leg.provenance_unknown"] * 4),
    "stale_null_vintage": (lambda d: (v_stale(d), d["legs"]["status"].update(content_vintage=None), d)[-1],
                           ["leg.provenance_unknown"]),
    "unknown_labelled_published": (lambda d: (v_unknown_no_provenance(d),
                                              d["legs"]["experts.cbs_weekly"].update(label="published"), d)[-1],
                                   ["leg.provenance_unknown"] * 4),
    # A malformed scoring list is reported, not raised (JEG-1267).
    "scoring_object_entry": (lambda d: (espn(d).update(scoring=[{}]), d)[-1], ["field.type"]),
    "scoring_list_entry": (lambda d: (espn(d).update(scoring=[[]]), d)[-1], ["field.type"]),
    "scoring_mixed_entry": (lambda d: (espn(d).update(scoring=["half_ppr", {}]), d)[-1], ["field.type"]),
}


def render(doc: dict) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, allow_nan=True) + "\n"


def build() -> dict[str, str]:
    """Relative path -> file text, for every fixture file."""
    out: dict[str, str] = {}
    expected: dict[str, dict] = {}
    for name, fn in VALID.items():
        out[f"valid/{name}.json"] = render(fn(base()))
        expected[f"valid/{name}.json"] = {"errors": [], "warnings": VALID_WARNINGS.get(name, [])}
    for name, (fn, codes) in INVALID.items():
        out[f"invalid/{name}.json"] = render(fn(base()))
        expected[f"invalid/{name}.json"] = {"errors": codes, "warnings": []}
    out["expected.json"] = json.dumps(expected, indent=2, sort_keys=True) + "\n"
    return out


def main() -> None:
    for rel, text in build().items():
        path = HERE / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(f"wrote {len(build())} files under {HERE}")


if __name__ == "__main__":
    main()
