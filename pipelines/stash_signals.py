#!/usr/bin/env python3
"""Stash signals outside the pie (JEG-526 handcuff contingency, JEG-529 waiver upside).

A separate series from DDF Value (MR-21: option value is a signal, not pie).
Nothing here feeds value_reference.py's pie, DDF Value or Indexed; this module
only reads the finished pipeline result and the players file.

JEG-526, the handcuff contingency (ES-13.1, MR-26 option b). For a running
back whose own NFL team's lead back is ahead of him on the depth chart:

    contingent = (1 - b) * m_lead * (1 - m_i) * (promoted - w)+ * P(promoted > l)

b is the bye probability, m_lead and m_i the lead back's and the backup's
forward missed-week hazards (config/lineup_parameters.json), w the waiver line,
l the starter line, and `promoted` the measured level a backup plays at when
the lead back misses: a multiple of the starter line, by lead-back tier
(config/handcuff_jump.json, re-derived by tools/handcuff_jump.py). Points of
surplus per week that reach a lineup, comparable to the pie's own per-player
`lineup_share * (x - w)`.

JEG-529, the bar a bench player must clear. The best free agents' own option,
`avail * E[(X - w)+ ; X > l]` per week (the convex form MR-21 keeps out of the
pie), per position: the max and the mean of the top three. A bench player's
hold value is `lineup_share * (x - w)` (plus the handcuff term for a back
behind a lead back). Where hold < the best free agent's option, the bench
player is a drop candidate. Display only.

Usage: python3 pipelines/stash_signals.py [--settings ppr/12,half_ppr/10] [--out output/stash-signals.json]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import value_reference as ref  # noqa: E402
from expected_starts_model import band_surplus  # noqa: E402

SCHEMA = "stash-signals/1"
JUMP_CONFIG = REPO / "config" / "handcuff_jump.json"
OUT = REPO / "output" / "stash-signals.json"
SOURCE = "espn"                      # the full-coverage projection source (ranks past the roster line)
NOT_ON_A_NFL_ROSTER = ("injured_reserve", "pup", "practice_squad", "free_agent", "suspended")
TOP_K = 3


def contingent_points(bye: float, m_lead: float, m_self: float, promoted: float, waiver: float,
                      p_start: float) -> float:
    """The MR-26 term: surplus points per week a backup adds because his lead back may miss."""
    return (1.0 - bye) * m_lead * (1.0 - m_self) * max(0.0, promoted - waiver) * p_start


def promoted_level(starter_line: float, lead_is_top: bool, cfg: dict) -> float:
    ratios = cfg["promoted_to_starter_line"]
    return starter_line * (ratios["top12"] if lead_is_top else ratios["all"])


def p_projected_to_start(level: float, line: float, sig_rel: float, sig_floor: float) -> float:
    """P(a back projected at `level` clears the starter line), the same normal the pie uses."""
    sd = max(sig_rel * level, sig_floor) if level > 0 else sig_floor
    return ref._p_between(level, sd, line, math.inf)


def load_jump_config(path: Path = JUMP_CONFIG) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def team_backs(players: list, ppg_of) -> dict:
    """team -> {"lead", "backup", "basis"} for running backs on NFL rosters.

    Sleeper depth_chart_order decides when both backs carry it; otherwise the
    higher projection leads (basis says which). A lead back who is out (IR, PUP)
    is left out of the ordering: the backup is already the lead and his
    projection prices that."""
    by_team: dict = {}
    for p in players:
        if p.get("pos") != "RB" or not p.get("team"):
            continue
        if p.get("roster_status") in NOT_ON_A_NFL_ROSTER:
            continue
        x = ppg_of(p)
        if not x or x <= 0:
            continue
        by_team.setdefault(p["team"], []).append(p)
    out = {}
    for team, rows in by_team.items():
        ordered = sorted(rows, key=lambda p: (p.get("depth_chart_order") is None,
                                              p.get("depth_chart_order") or 0, -ppg_of(p)))
        if len(ordered) < 2:
            continue
        lead, backup = ordered[0], ordered[1]
        charted = lead.get("depth_chart_order") is not None and backup.get("depth_chart_order") is not None
        if ppg_of(backup) > ppg_of(lead):
            # a stale chart (the "backup" out-projects the "lead"): trust the projections
            lead, backup, charted = backup, lead, False
        out[team] = {"lead": lead, "backup": backup, "basis": "depth_chart" if charted else "projection_rank"}
    return out


def contingent_for_setting(res: dict, players: list, ppg_of, cfg: dict, source: str = SOURCE) -> dict:
    """player_key -> contingent record for the backup behind each team's lead back."""
    pos = res["sources"][source]["positions"]["RB"]
    lineup = res["lineup"]
    lp = lineup["positions"]["RB"]
    w, line, bye = pos["waiver_value"], pos["starter_line"], lineup["bye"]
    ranked = sorted((ppg_of(p) for p in players if p.get("pos") == "RB" and ppg_of(p)), reverse=True)
    top_cut = ranked[cfg["lead_back_top_cutoff"] - 1] if len(ranked) >= cfg["lead_back_top_cutoff"] else ranked[-1]
    rows = res["rows"]
    out = {}
    for team, t in team_backs(players, ppg_of).items():
        lead, back = t["lead"], t["backup"]
        top = ppg_of(lead) >= top_cut
        promoted = max(ppg_of(back), promoted_level(line, top, cfg))
        p_start = p_projected_to_start(promoted, line, lp["sigma_rel"], lp["sigma_floor"])
        points = contingent_points(bye, lp["m"], lp["m"], promoted, w, p_start)
        p_promoted_start = (1.0 - bye) * lp["m"] * (1.0 - lp["m"]) * p_start
        key = back.get("player_key")
        own = (rows.get(key) or {}).get("start_worthy") or 0.0
        out[key] = {"name": back.get("name"), "team": team, "lead_back": lead.get("name"),
                    "lead_tier": "top12" if top else "other", "basis": t["basis"],
                    "promoted_level": round(promoted, 3), "p_start_at_promoted": round(p_start, 4),
                    "contingent_points": round(points, 4),
                    "p_start_if_lead_misses": round(p_promoted_start, 4),
                    "own_p_start": round(own, 4),
                    "stash_signal": round(1.0 - (1.0 - own) * (1.0 - p_promoted_start), 4)}
    return out


def waiver_bar(res: dict, source: str = SOURCE) -> dict:
    """JEG-529: per position, the best free agents' option and each bench player's hold value."""
    src = res["sources"][source]
    out = {}
    for p, info in src["positions"].items():
        if info.get("waiver_value") is None:
            continue
        w, line, avail = info["waiver_value"], info["starter_line"], info.get("avail", 1.0)
        lp = info.get("lineup") or {}
        options, bench = [], []
        for key, rec in src["players"].items():
            if rec["pos"] != p:
                continue
            x = rec["native"]
            sd = max(lp.get("sigma_rel", 0.0) * x, lp.get("sigma_floor", 0.0)) if x > 0 else lp.get("sigma_floor", 0.0)
            if rec["role"] == "waiver":
                options.append((avail * band_surplus(x, sd, w, line, math.inf), key))
            elif rec["role"] == "bench":
                bench.append((key, x, (rec.get("lineup_share") or 0.0) * max(0.0, x - w)))
        options.sort(reverse=True)
        top = options[:TOP_K]
        out[p] = {"waiver_value": w, "starter_line": line,
                  "best_option": round(top[0][0], 4) if top else 0.0,
                  "best_player": top[0][1] if top else None,
                  "top_k_option": round(sum(o for o, _ in top) / len(top), 4) if top else 0.0,
                  "bench": {k: {"ppg": round(x, 3), "hold": round(h, 4)} for k, x, h in bench}}
    return out


def build(scoring: str, teams: int, cfg: dict, players: list, inp=None, hist=None) -> dict:
    inp = inp or ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    s = ref.Setting(inp, scoring, teams, hist=hist)
    res = s.result()
    field_name = ref.PPG_FIELD[SOURCE]

    def ppg_of(p):
        v = (p.get(field_name) or {}).get(scoring)
        return v if isinstance(v, (int, float)) and v > 0 else None

    cont = contingent_for_setting(res, players, ppg_of, cfg)
    bar = waiver_bar(res)
    for pos, b in bar.items():
        for key, h in b["bench"].items():
            extra = cont.get(key, {}).get("contingent_points", 0.0) if pos == "RB" else 0.0
            h["contingent"] = extra
            h["hold_with_contingent"] = round(h["hold"] + extra, 4)
            h["drop_candidate"] = h["hold_with_contingent"] < b["best_option"]
            h["name"] = inp.players.get(key, {}).get("name")
    return {"scoring": scoring, "teams": teams, "source": SOURCE, "bye": res["lineup"]["bye"],
            "contingent": {str(k): v for k, v in sorted(cont.items(), key=lambda kv: -kv[1]["contingent_points"])},
            "waiver_bar": bar}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--settings", default="ppr/12", help="comma list like ppr/12,half_ppr/10")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    cfg = load_jump_config()
    players = json.loads(ref.PLAYERS.read_text(encoding="utf-8"))["players"]
    inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS)
    settings = [(x.split("/")[0], int(x.split("/")[1])) for x in args.settings.split(",")]
    doc = {"schema": SCHEMA, "jump_config": cfg,
           "settings": [build(sc, t, cfg, players, inp=inp) for sc, t in settings]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    for s in doc["settings"]:
        top = list(s["contingent"].values())[:8]
        print(f"{s['scoring']}/{s['teams']}: top handcuffs by contingent points")
        for r in top:
            print(f"  {r['name']} ({r['team']}, behind {r['lead_back']}, {r['lead_tier']}, {r['basis']}): "
                  f"{r['contingent_points']:.2f} pts/wk, stash {r['stash_signal']:.2f} (own {r['own_p_start']:.2f})")
        for pos, b in s["waiver_bar"].items():
            drops = sum(1 for h in b["bench"].values() if h["drop_candidate"])
            print(f"  {pos}: best free-agent option {b['best_option']:.2f}, top-{TOP_K} {b['top_k_option']:.2f}, "
                  f"bench below it {drops}/{len(b['bench'])}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
