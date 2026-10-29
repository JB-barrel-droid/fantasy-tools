"""Build the JEG-1188 league-level fixtures from two real Yahoo leagues.

Repro:  python3 tools/build_league_level_fixtures.py

Inputs:
  tests/fixtures/league_levels/raw/*_rosters_2026-10-29.json
      Current Yahoo rosters (Flaim get_roster, read only), every team, with
      each player's slot (QB, RB, WR, TE, W/R/T, BN, IR, K, DEF). Yahoo team
      ids only: no team or owner names.
  The repo's live value inputs (pipelines/spec_reference/pipeline_live.load),
      half PPR, 12 teams, 1QB, the current week, as the page reads them.

Baseline: --baseline <value-model.js> also runs that engine (the one before
JEG-1188, e.g. `git show d1d108c3:app/trade-value-chart/assets/value-model.js`)
with no league loaded (--baseline-label names it) and stores its allocation and every player's DDF Value
under "baseline_no_league"; the tests require today's engine to match it.

Output: tests/fixtures/league_levels/<league>.json in the worked-example
driver shape (setting, players, inputs, included, variant_live.lineup) plus
"league": the rosters matched to player keys and an accounting of every
roster spot. Values are frozen at build time, so the tests are exact; rerun
this script to refresh them (the tests then pin new numbers).
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from spec_reference import pipeline_live as pl, value_pipeline as vp  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "league_levels"
SKILL = ("QB", "RB", "WR", "TE")
FLEX_SLOTS = {"W/R/T": ("RB", "WR", "TE"), "W/R": ("RB", "WR"), "Q/W/R/T": SKILL}
LEAGUES = {
    "uso": {"raw": "uso_rosters_2026-10-29.json", "scoring": "half_ppr", "mine": "2"},
    "charlotte": {"raw": "charlotte_rosters_2026-10-29.json", "scoring": "half_ppr", "mine": "11"},
}
# Yahoo spelling -> the value inputs' spelling, where they differ.
ALIASES = {"Kenny Gainwell": "Kenneth Gainwell"}


def norm(name: str) -> str:
    n = name.lower().replace(".", "").replace("'", "").replace("’", "")
    n = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", n)
    return re.sub(r"\s+", " ", n).strip()


def build(league: str, cfg: dict, data: dict, lineup: dict, commit: str) -> dict:
    raw = json.loads((OUT / "raw" / cfg["raw"]).read_text())
    rs = raw["roster_slots"]
    teams = int(raw["teams_count"])
    current, hidden, included = {}, [], []
    eligible = []
    for s in pl.SOURCE_ORDER:
        nat = pl.current_natives(data, s, cfg["scoring"], teams, 0, {})
        reason = pl.eligibility(data, s, nat)
        if not nat:
            continue
        fam = vp.PROJECTION if s in pl.PROJECTIONS else vp.CHART
        current[s] = {"family": fam, "values": {str(k): v for k, v in nat.items()},
                      "status": reason or "included"}
        if reason:
            continue
        eligible.append(s)
        if pl.source_hidden(data, s):
            hidden.append(s)
            current[s]["status"] = "hidden"
    included = list(eligible)
    keys = sorted({k for s in current.values() for k in s["values"]}, key=int)
    pos_of = {str(k): p for k, p in data["pos_of"].items()}
    players = {k: {"name": data["names"].get(int(k)) or data["names"].get(k), "pos": pos_of[k]}
               for k in keys if pos_of.get(k) in SKILL}
    byname = collections.defaultdict(list)
    for k, p in players.items():
        if p["name"]:
            byname[(norm(p["name"]), p["pos"])].append(k)
    flex = sum(n for s, n in rs.items() if s in FLEX_SLOTS)
    out_teams, accounting = [], collections.Counter()
    for t in raw["teams"]:
        plist = []
        for pl_ in t["players"]:
            pos, slot = pl_["pos"], pl_["slot"]
            entry = {"name": pl_["name"], "pos": pos, "slot": slot}
            if pos in SKILL:
                hits = byname.get((norm(ALIASES.get(pl_["name"], pl_["name"])), pos), [])
                entry["key"] = hits[0] if len(hits) == 1 else None
            plist.append(entry)
            kind = ("k_def" if pos not in SKILL else "unresolved" if entry.get("key") is None else
                    "reserve" if slot == "IR" else "bench" if slot == "BN" else "starting")
            accounting[f"{kind}:{slot}"] += 1
        out_teams.append({"id": str(t["team_id"]), "players": plist})
    bench_seats = int(rs.get("BN", 0)) * teams
    bn_skill = sum(v for k, v in accounting.items() if k in ("bench:BN", "unresolved:BN"))
    bn_kdef = accounting.get("k_def:BN", 0)
    start_slots = sum(int(rs.get(p, 0)) for p in SKILL) + flex
    filled_start = sum(v for k, v in accounting.items()
                       if k.split(":")[0] in ("starting", "unresolved") and k.split(":")[1] not in ("BN", "IR"))
    acct = {
        "bench_seats_configured": bench_seats,
        "bench_seats_skill_players": bn_skill,
        "bench_seats_k_def": bn_kdef,
        "bench_seats_empty": bench_seats - bn_skill - bn_kdef,
        "reserve_seats_configured": int(rs.get("IR", 0)) * teams,
        "reserve_seats_used": sum(v for k, v in accounting.items() if k.endswith(":IR")),
        "starting_skill_slots_configured": start_slots * teams,
        "starting_skill_slots_filled": filled_start,
        "k_def_players": sum(v for k, v in accounting.items() if k.startswith("k_def:")),
        "unresolved_players": sum(v for k, v in accounting.items() if k.startswith("unresolved:")),
        "by_kind_and_slot": dict(sorted(accounting.items())),
    }
    return {
        "schema": "league-levels/1",
        "provenance": {
            "rosters": f"Yahoo current rosters via Flaim get_roster (read only), fetched {raw['fetched']}; "
                       "Yahoo team ids only, no team or owner names",
            "values": f"pipelines/spec_reference/pipeline_live inputs at commit {commit}, "
                      f"{cfg['scoring']}, {teams} teams, 1QB, current week, built {dt.date.today()}",
            "repro": "python3 tools/build_league_level_fixtures.py",
        },
        "roster_slots": rs,
        "mine": cfg["mine"],
        "setting": {"teams": teams, "slots": {p: int(rs.get(p, 0)) for p in SKILL}, "flex": flex,
                    "flex_eligible": ["RB", "WR", "TE"], "superflex": 0,
                    "bench_per_team": int(rs.get("BN", 0)), "bench_share": vp.DEFAULT_BENCH_SHARE},
        "players": players,
        "inputs": current,
        "included": included,
        "hidden": hidden,
        "variant_live": {"lineup": lineup},
        "league": {"teams": out_teams, "accounting": acct},
    }


def baseline(engine: str, label: str, path: Path) -> dict:
    proc = subprocess.run(["node", str(ROOT / "tests" / "value_pipeline_driver.js"), engine, str(path),
                           "--variant", "variant_live"], capture_output=True, text=True, check=True)
    out = json.loads(proc.stdout)
    return {"engine": label, "allocation": out["allocation"],
            "ddf_value": {k: (None if r["ddf_blended"]["value"] is None else round(r["ddf_blended"]["value"], 9))
                          for k, r in out["rows"].items()}}


def main() -> None:
    engine = sys.argv[sys.argv.index("--baseline") + 1] if "--baseline" in sys.argv else None
    label = sys.argv[sys.argv.index("--baseline-label") + 1] if "--baseline-label" in sys.argv else str(engine)
    data = pl.load(pl.default_paths())
    lineup = vp.resolve_lineup(pl.lineup_config())
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip()
    for league, cfg in LEAGUES.items():
        doc = build(league, cfg, data, lineup, commit)
        path = OUT / f"{league}.json"
        path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        if engine:
            doc["baseline_no_league"] = baseline(engine, label, path)
            path.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
        print(path.relative_to(ROOT), json.dumps(doc["league"]["accounting"]))


if __name__ == "__main__":
    main()
