#!/usr/bin/env python3
"""JEG-1171: freeze the stored inputs behind the CBS ROS week-8 divergence warn.

Read-only. Every number comes from files already committed to git (no network,
no Supabase, no new source capture):

  * e2c191c (2026-10-27 10:59Z): the commit that published
    dist/modules/source-divergence.json with the warn (fixture built
    2026-10-26T15:42:37Z), its comparison fixture, players.json, history
    index and the 2026-10-26 CBS ROS legs (bake ddf-20261026-cbsros-*-12t-0p15).
  * data/raw/sources/cbsros/2026-09-30/snapshot.json: the only CBS ROS raw
    snapshot with stat components in the repo (the 2026-10-26 raw is not stored).
  * ca51f2f (2026-10-29 15:03Z): a later rebuild (CBS vintage 2026-10-29), used
    only as the wrong-week mutation.

    python3 docs/research/JEG-1171/extract_fixtures.py

writes tests/fixtures/JEG-1171/*.json.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "tests" / "fixtures" / "JEG-1171"
ALERT_COMMIT = "e2c191c"
LATER_COMMIT = "ca51f2f"
GROUP = ("espn", "cbsros", "razzball")
COMBOS = ("standard_12", "half_12", "full_12")
LEG_SCORING = {"standard_12": "standard", "half_12": "half_ppr", "full_12": "ppr"}
SAMPLES = ("joe burrow", "david montgomery", "jalen coker", "tyler warren", "bijan robinson")
EDGE = ("aaron rodgers", "efton chism iii")  # CBS priced 0.0 / CBS missing
RAW_0930 = ("Josh Allen", "Trevor Lawrence", "Brock Purdy", "Jahmyr Gibbs", "Bijan Robinson",
            "Jonathan Taylor", "Jaxon Smith-Njigba", "Ja'Marr Chase", "Brock Bowers", "Trey McBride")


def show(commit: str, path: str):
    return json.loads(subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPO, check=True,
                                     capture_output=True, text=True).stdout)


def projection_slice(fixture: dict, positive_only: bool) -> dict:
    """The three projection sources' shown values per 12-team combo, as stored."""
    out = {}
    for s in GROUP:
        sec = fixture["sources"][s]
        out[s] = {"vintage": sec.get("vintage") or (sec.get("espn_status") or {}).get("vintage"),
                  "source_url": sec.get("source_url"), "week_designated": sec.get("week_designated"),
                  "validationHold": sec.get("validationHold"), "combos": {}}
        for ck in COMBOS:
            vals = sec["combos"][ck]["values"]
            out[s]["combos"][ck] = {n: v for n, v in vals.items() if not positive_only or (v or 0) > 0}
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fx = show(ALERT_COMMIT, "data/fixtures/current/comparison-sources-data.json")
    players = show(ALERT_COMMIT, "data/fixtures/current/players.json")["players"]
    report = show(ALERT_COMMIT, "dist/modules/source-divergence.json")
    index = show(ALERT_COMMIT, "data/history/index.json")
    pos = {p["player_key"]: p.get("pos") for p in players}

    sl = projection_slice(fx, positive_only=True)
    names = {n for s in sl.values() for c in s["combos"].values() for n in c}
    keys = {n: fx["player_keys"][n] for n in sorted(names) if n in fx["player_keys"]}
    cb = fx["sources"]["cbsros"]
    alert = {
        "_about": "Frozen from git (see docs/research/JEG-1171/extract_fixtures.py). Positive shown values only, "
                  "which is all the divergence check reads (by_key drops <= 0 and unmatched names).",
        "commit": ALERT_COMMIT, "fixture_built_at": fx["built_at"], "content_week": index["content_week"],
        "served": {s: index["served"][s] for s in GROUP},
        "cbsros_section": {k: cb.get(k) for k in ("source_url", "vintage", "lineage", "method", "snapshot_id",
                                                  "week_designated", "validationHold")},
        "cbsros_index_total": {ck: {p: x["factor"] for p, x in cb["combos"][ck]["index_total"].items()}
                               for ck in COMBOS},
        "published_report_cbsros": {k: report["sources"]["cbsros"][k] for k in
                                    ("status", "headline_combo", "n", "bias", "outlier_rate", "message", "week")}
                                   | {"generated_at": report["generated_at"],
                                      "combos": {ck: {k: v for k, v in c.items() if k in ("n", "bias", "mad", "outlier_rate", "outliers")}
                                                 for ck, c in report["sources"]["cbsros"]["combos"].items()}},
        "player_keys": keys,
        "positions": {str(k): pos.get(k) for k in sorted(set(keys.values()))},
        "sources": sl,
    }
    (OUT / "alert_inputs_e2c191c.json").write_text(json.dumps(alert, indent=1, sort_keys=True) + "\n")

    trace = {"_about": "Native (CBS per-game) -> two-tier raw -> x scale_70_over_max -> fixture value, "
                       "for five sample players and two edge cases, from the 2026-10-26 CBS legs and the "
                       "e2c191c fixture.", "commit": ALERT_COMMIT, "combos": {}}
    for ck, sc in LEG_SCORING.items():
        leg = show(ALERT_COMMIT, f"data/ddf-two-tier/ddf-20261026-cbsros-{sc}-12t-0p15/ddf_leg_cbsros.json")
        rows = {v["player_norm"]: v for v in leg["values"]}
        trace["combos"][ck] = {
            "bake_id": leg["bake_id"], "leg_generated_at": leg["generated_at"],
            "snapshot_date": leg["inputs"]["cbsros_snapshot_date"],
            "snapshot_sha256": leg["inputs"]["cbsros_snapshot_sha256"],
            "scale_70_over_max": leg["scale_70_over_max"],
            "calibration": {p: {k: c[k] for k in ("rw", "rs", "tau", "pb", "ps")} for p, c in leg["calibration"].items()},
            "players": {n: ({k: rows[n][k] for k in ("pos", "ppg", "raw_value", "value", "tier")} if n in rows else {})
                        | {"fixture_native": cb["combos"][ck]["native"].get(n),
                           "fixture_value": cb["combos"][ck]["values"].get(n),
                           "others": {s: fx["sources"][s]["combos"][ck]["values"].get(n) for s in ("espn", "razzball")},
                           "others_native": {s: fx["sources"][s]["combos"][ck]["native"].get(n) for s in ("espn", "razzball")}}
                        for n in SAMPLES + EDGE},
        }
    (OUT / "cbsros_trace_e2c191c.json").write_text(json.dumps(trace, indent=1, sort_keys=True) + "\n")

    raw = json.loads((REPO / "data/raw/sources/cbsros/2026-09-30/snapshot.json").read_text())
    rows = [r for r in raw["rows"] if r["player_name"] in RAW_0930]
    (OUT / "cbsros_raw_2026-09-30_rows.json").write_text(json.dumps(
        {"_about": "Ten rows copied as stored from data/raw/sources/cbsros/2026-09-30/snapshot.json "
                   "(CBS nonppr ROS totals with stat components). The only stored CBS raw with components.",
         "vintage_date": raw["vintage_date"], "scoring_note": raw["scoring_note"], "rows": rows},
        indent=1, sort_keys=True) + "\n")

    later = show(LATER_COMMIT, "data/fixtures/current/comparison-sources-data.json")
    (OUT / "later_inputs_ca51f2f.json").write_text(json.dumps(
        {"_about": "Wrong-week mutation only: the 2026-10-29 rebuild (CBS vintage 2026-10-29).",
         "commit": LATER_COMMIT, "fixture_built_at": later["built_at"],
         "player_keys": {n: later["player_keys"][n] for n in sorted({n for s in projection_slice(later, True).values()
                                                                      for c in s["combos"].values() for n in c})
                         if n in later["player_keys"]},
         "sources": projection_slice(later, positive_only=True)}, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
