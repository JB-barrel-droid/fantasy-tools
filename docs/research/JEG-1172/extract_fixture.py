#!/usr/bin/env python3
"""JEG-1172: freeze the FantasyPros week-8 divergence evidence into an offline fixture.

Read-only. Reads committed files at two git revisions with `git show` and
writes tests/fixtures/JEG-1172/fantasypros-w8-trace.json. It copies values
already stored in the repo; it never fetches or invents a source capture.

  FLAGGED = e2c191c  the commit whose dist/modules/source-divergence.json raised
                     divergence:fantasypros:w8 (fixture built 2026-10-26T15:42Z)
  CURRENT = b863069  main when this diagnosis ran (fixture built 2026-10-29T14:09Z),
                     serving the FantasyPros Week 8 article. The Week 8 article first
                     reached the fixture earlier, at e55755c (built 2026-10-28T13:19Z).

    python3 docs/research/JEG-1172/extract_fixture.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "tests" / "fixtures" / "JEG-1172" / "fantasypros-w8-trace.json"
FLAGGED, CURRENT = "e2c191c", "b863069"
CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
SCORINGS = ("standard", "half", "full")
HISTORY_SCORING = {"standard": "standard", "half": "half_ppr", "full": "ppr"}
SAMPLES = ("ceedee lamb", "malik nabers", "christian mccaffrey", "josh allen", "brock bowers")
# Controls for missing versus zero: priced by the other charts but absent from
# FantasyPros, and a USA Today row stored as 0.
CONTROLS = ("davante adams", "carson wentz")
META = ("url", "week_designated", "content_vintage", "fetched_at", "promoted_at", "claimed_settings")


def show(rev: str, path: str) -> dict:
    return json.loads(subprocess.check_output(["git", "show", f"{rev}:{path}"], cwd=REPO))


def combo_key(source: str, scoring: str) -> str:
    return f"{scoring}_12_qb1" if source == "fantasycalc" else f"{scoring}_12"


def snapshot(rev: str, names) -> dict:
    fixture = show(rev, "data/fixtures/current/comparison-sources-data.json")
    index = show(rev, "data/history/index.json")
    players = {p["player_key"]: p for p in show(rev, "data/fixtures/current/players.json")["players"]}
    keys = fixture["player_keys"]
    out = {
        "git_rev": rev,
        "fixture_built_at": fixture.get("built_at"),
        "content_week": index.get("content_week"),
        "served": {s: {k: index["served"][s].get(k) for k in ("label_week", "week", "fingerprint")} for s in CHARTS},
        "sources": {},
        "players": {},
    }
    for s in CHARTS:
        src = fixture["sources"][s]
        out["sources"][s] = {k: src.get(k) for k in META if k in src}
    fp_combos = fixture["sources"]["fantasypros"]["combos"]
    out["sources"]["fantasypros"]["indexed_factor"] = {
        sc: fp_combos[combo_key("fantasypros", sc)]["fit"]["order_preserving_rescale"]["factor"] for sc in SCORINGS}
    for name in names:
        key = keys.get(name)
        row = {"player_key": key, "pos": (players.get(key) or {}).get("pos"),
               "fantasypros_native": fp_combos["half_12"]["native"].get(name),
               "fantasypros_native_2qb": fp_combos["half_12"].get("native_superflex", {}).get(name),
               "shown": {}}
        for sc in SCORINGS:
            row["shown"][sc] = {}
            for s in CHARTS:
                combo = fixture["sources"][s]["combos"][combo_key(s, sc)]
                value = (combo.get("values") or combo.get("reindexed") or {}).get(name)
                row["shown"][sc][s] = value  # None = missing from that chart; 0 stays 0
            row["shown"][sc]["fantasypros_native_this_combo"] = fp_combos[combo_key("fantasypros", sc)]["native"].get(name)
        out["players"][name] = row
    return out


def main() -> int:
    names = SAMPLES + CONTROLS
    flagged = snapshot(FLAGGED, names)
    week7 = show(FLAGGED, "data/history/week-7.json")["sources"]["fantasypros"]
    flagged["history_week7_fantasypros"] = {
        "fingerprint": week7.get("fingerprint"), "origin": week7.get("origin"),
        "natives": {name: {sc: week7["natives"][HISTORY_SCORING[sc]].get(str(row["player_key"]))
                           for sc in SCORINGS}
                    for name, row in flagged["players"].items() if row["player_key"] is not None},
    }
    # Whole FantasyPros population of the flagged run against frozen week 7,
    # keyed by player_key, so the 178-of-178 claim is asserted, not hand-checked.
    fixture = show(FLAGGED, "data/fixtures/current/comparison-sources-data.json")
    keys = fixture["player_keys"]
    fp_combos = fixture["sources"]["fantasypros"]["combos"]
    flagged["population"] = {
        "flagged_natives": {sc: {str(keys[n]): v for n, v in fp_combos[combo_key("fantasypros", sc)]["native"].items()
                                 if keys.get(n) is not None}
                            for sc in SCORINGS},
        "unkeyed_names": sorted(n for n in fp_combos["half_12"]["native"] if keys.get(n) is None),
        "history_week7_natives": {sc: week7["natives"][HISTORY_SCORING[sc]] for sc in SCORINGS},
    }
    report = show(FLAGGED, "dist/modules/source-divergence.json")["sources"]["fantasypros"]
    flagged["report"] = {
        "status": report["status"], "headline_combo": report["headline_combo"], "reasons": report["reasons"],
        "combos": {c: {k: v[k] for k in ("n", "bias", "outlier_rate", "outliers", "status", "examples")}
                   | {"baseline": v["baseline"], "prior_weeks": v["prior_weeks"]}
                   for c, v in report["combos"].items()},
    }
    doc = {
        "about": ("JEG-1172 frozen evidence. Values copied from committed repo files at two git revisions by "
                  "docs/research/JEG-1172/extract_fixture.py; no source page was fetched and nothing is "
                  "synthesized. null = the chart does not list the player; 0 = the chart stores 0."),
        "player_names": {"samples": list(SAMPLES), "controls": list(CONTROLS)},
        "flagged_run": flagged,
        "current_run": snapshot(CURRENT, names),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
