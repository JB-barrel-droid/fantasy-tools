#!/usr/bin/env python3
"""JEG-1171 COUNTERFACTUAL, diagnosis only: how much of the week-8 CBS ROS warn
is the scoring basis?

Takes the stored 2026-10-26 CBS legs (git e2c191c), divides each player's
non-reception per-game points by the position factor measured on the stored
2026-09-30 raw (CBS fpts / 4-pt fractional recompute: QB 1.123, RB 0.857,
WR 0.892, TE 0.905), adds the reception points back, re-prices with the
unchanged CBS leg code, and re-runs the unchanged divergence check. Nothing is
written to the repo; the synthetic inputs live in a temp dir and are NOT a
source capture. A position-wide factor is a rough stand-in for a per-player
rescore, which needs the 2026-10-26 stat components that are not stored.

    python3 docs/research/JEG-1171/counterfactual_rescore.py           # rescored
    python3 docs/research/JEG-1171/counterfactual_rescore.py --identity  # control
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "pipelines"))
import build_cbsros_ddf_leg as leg_mod  # noqa: E402
import check_source_divergence as sd  # noqa: E402

COMMIT = "e2c191c"
FACTOR = {"QB": 1.123, "RB": 0.857, "WR": 0.892, "TE": 0.905}
COMBOS = (("standard", "standard_12", 0.0), ("half_ppr", "half_12", 0.5), ("ppr", "full_12", 1.0))


def show(path: str) -> str:
    return subprocess.run(["git", "show", f"{COMMIT}:{path}"], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout


def main() -> None:
    factor = {p: 1.0 for p in FACTOR} if "--identity" in sys.argv else FACTOR
    with tempfile.TemporaryDirectory() as tmp:
        w = Path(tmp)
        (w / "history").mkdir()
        fixture = w / "comparison-sources-data.json"
        fixture.write_text(show("data/fixtures/current/comparison-sources-data.json"))
        (w / "players.json").write_text(show("data/fixtures/current/players.json"))
        (w / "history" / "index.json").write_text(show("data/history/index.json"))
        legs = {sc: json.loads(show(f"data/ddf-two-tier/ddf-20261026-cbsros-{sc}-12t-0p15/ddf_leg_cbsros.json"))
                for sc, _, _ in COMBOS}
        std = {v["player_norm"]: v for v in legs["standard"]["values"]}
        ppr = {v["player_norm"]: v["ppg"] for v in legs["ppr"]["values"]}
        fx = json.loads(fixture.read_text())
        out = copy.deepcopy(fx)
        for sc, ck, per_rec in COMBOS:
            rows = []
            for n, v in std.items():
                x = v["ppg"] / factor[v["pos"]] + per_rec * (ppr[n] - v["ppg"])
                rows.append({"player_name": v["player"], "player_norm": n, "pos": v["pos"], "team": v["team"],
                             "per_game_standard": x, "per_game_half_ppr": x, "per_game_ppr": x})
            snap = w / f"counterfactual_{sc}.json"
            snap.write_text(json.dumps({"vintage_date": "2026-10-26", "rows": rows}))
            leg = leg_mod.build_leg(snap, fixture, sc, 12, 0.15)
            out["sources"]["cbsros"]["combos"][ck]["values"] = {v["player_norm"]: round(v["value"], 1)
                                                                for v in leg["values"]}
        cf = w / "counterfactual_fixture.json"
        cf.write_text(json.dumps(out))
        report = sd.run(fixture_path=cf, players_path=w / "players.json", history_dir=w / "history",
                        resolutions_path=w / "none.json")
    for s in ("espn", "cbsros", "razzball"):
        row = report["sources"][s]
        print(s, row["status"], {k: (c["n"], c["outlier_rate"], c["bias"]) for k, c in row["combos"].items()})


if __name__ == "__main__":
    main()
