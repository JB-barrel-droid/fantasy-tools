"""Regenerate lottery/results/<board_stem>.md (+ .json) from v_lottery_board.

Splits the board into two delineated sections per the availability tier:
  1. "Lottery tickets"  — availability_tier = 'available' (top 25)
  2. "Upside stashes"   — availability_tier = 'likely-owned' (top 15)
plus a compact "On the radar" list for the 'unknown' tier.

Per-player format follows the design doc, extended with: health status
(IR badge), conditional points/game if the breakout hits, hit window
(weeks) + valuable-role duration range, and the lottery-implied trade
value on the chart's 0-70 scale. Also writes <board_stem>.json —
the machine-readable data contract for the dashboard (and the future
trade-chart tab seam). The board week (label + filenames) is derived from
bin/board_week.py — never hardcoded.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parent.parent  # waiver_wire/pipeline
sys.path.insert(0, str(_PIPELINE / "engine"))
sys.path.insert(0, str(_PIPELINE / "bin"))
from sb_rest import latest_as_of, board_at  # noqa: E402
from board_week import board_stem, board_week_label  # noqa: E402

LOT = str(Path(__file__).resolve().parent.parent)  # waiver_wire/pipeline
N_TICKETS, N_STASHES = 25, 15


def fmt_pct(x):
    return f"{float(x or 0):.0%}"


def status_badge(r):
    st = r["status"] or "Healthy"
    if st in ("IR", "PUP"):
        return (f"🏥 **{st}** — stash, not a plug-and-play add"
                + (f" ({r['status_detail']})" if r["status_detail"] else ""))
    if st in ("Out", "Doubtful", "Questionable"):
        return f"⚠️ **{st}**" + (f" ({r['status_detail']})" if r["status_detail"] else "")
    if st == "Inactive":
        return "⚠️ **Inactive** (game-day inactive)"
    return None


def player_block(rank, r):
    cj = r["component_json"] or {}
    ej = r["explanation_json"] or {}
    lines = []
    a = lines.append
    paths = cj.get("paths") or []
    m = paths[0]["mechanism"] if paths else r["primary_mechanism"]
    cv = float((paths[0]["cond_vorp_pg"] if paths
                else r["cond_vorp_pg"]) or 0)
    badge = status_badge(r)
    two = " ⚡ **two ways to win**" if r.get("two_paths") else ""
    a(f"## {rank}. {r['player_name']} ({r['position']}, {r['team']}) — "
      f"Lottery Value: {float(r['lottery_score']):.1f}{two}")
    a("")
    if badge:
        a(f"- Status: {badge}")
    a(f"- Availability: **{r['availability_tier']}** · "
      f"ESPN {r['roster_pct'] if r['roster_pct'] is not None else 'n/a'}% rostered "
      f"({r['availability_conf']} confidence, {r['availability_source']})"
      + (f" · Sleeper adds 24h/7d: {r['adds_24h']}/{r['adds_7d']}"
         if (r["adds_7d"] or 0) > 0 else ""))
    a(f"- Current fantasy value: {float(r['current_use_vorp']):.1f} VORP "
      f"(ECR {float(cj.get('ecr_ppg') or 0):.1f}/g vs waiver-wire line "
      f"{float(cj.get('replacement_ppg') or 0):.1f}/g)")
    if paths:
        lead = paths[0]
        a(f"- Path to relevance: **{lead['path_to_relevance']}** "
          f"(blocker: {lead['blocker']})")
        for p in paths[1:]:
            a(f"- Also: **{p['path_to_relevance']}** "
              f"(P4 {fmt_pct(p['p4'])}, blocker: {p['blocker']})")
        per_path = " / ".join(
            f"{p['mechanism'][:4]} {fmt_pct(p['p4'])}" for p in paths)
    else:
        per_path = ""
    a(f"- Breakout probability: {fmt_pct(r['p1'])}/{fmt_pct(r['p2'])}/"
      f"{fmt_pct(r['p4'])}/{fmt_pct(r['p6'])} within 1/2/4/6 weeks "
      + (f"(by path: {per_path})" if per_path else ""))
    hs = (paths[0].get("hit_state") if paths else cj.get("hit_state")) or "marginal"
    hs_txt = ("marginal role gain — below the breakout bar, not a league-winner"
              if hs == "marginal" else "breakout")
    if m == "median":
        # Tucker rule (v0.6): no live catalyst — the honest card is the
        # median, not a fake "if he hits".
        a(f"- If he hits: n/a — **no live path to a bigger role** · median "
          f"projection {float(r['cond_points_pg'] or 0):.1f} PPR pts/game")
    elif m == "consolidation":
        # the conditional is median + vacated-target boost, not a role
        # value above the waiver line — say so explicitly.
        a(f"- If he hits: **{float(r['cond_points_pg'] or 0):.1f} PPR pts/game** "
          f"(+{cv:.1f} over his own median projection, from the sidelined "
          f"teammate's vacated targets) · {hs_txt}")
    else:
        a(f"- If he hits: **{float(r['cond_points_pg'] or 0):.1f} PPR pts/game** "
          f"(+{cv:.1f} over the waiver-wire line) · {hs_txt}")
    _dlo, _dhi, _dex = (float(r['duration_lo'] or 0),
                        float(r['duration_hi'] or 0),
                        float(r['duration_games'] or 0))
    _dur = ("about half a game" if _dhi < 1
            else f"~{_dlo:.0f}–{_dhi:.0f} games (expected {_dex:.1f})")
    if m != "median":
        a(f"- When: {r['hit_window'] or 'beyond the fantasy horizon (long shot)'}"
          f" · valuable for {_dur}")
        a(f"- Startability: {cj.get('startability', '')} "
          f"({cj.get('confirm_lag_games', 0)} games of proof netted out of the value)")
    if m == "contingent":
        if r.get("starter_name"):
            a(f"- The starter: **{r['starter_name']}** — "
              f"{(cj.get('starter_injury_sentence') or '').strip()}")
        mix = cj.get("contingent_injury_mix") or []
        named = [t for t in mix if t["bucket"] != "Other/unknown"][:3]
        unk = next((t for t in mix if t["bucket"] == "Other/unknown"), None)
        if named:
            types = "; ".join(
                f"{t['bucket']} ~{t['mean_games']:.0f} games out "
                f"({t['share']:.0%} of absences{'; thin data' if t.get('thin') else ''})"
                for t in named)
            extra = (f"; ~{unk['share']:.0%} untyped (mostly preseason IR stints, "
                     f"~{unk['mean_games']:.0f} games)" if unk else "")
            who = r.get("starter_name") or "the starter"
            a(f"- If {who} goes down: history says he's typically out "
              f"{float(r['duration_lo'] or 0):.0f}–{float(r['duration_hi'] or 0):.0f} "
              f"games. Usual culprits, 2024–25: {types}{extra}.")
    if paths:
        def _ptxt(i, p):
            _dd = p['duration_exp'] or 0
            _dt = "about half a game" if _dd < 1 else f"~{_dd:.0f} games"
            return (f"{i+1}) {p['mechanism']} — P4 {fmt_pct(p['p4'])}, "
                    f"if it hits ~{p['cond_points_pg']:.1f}/g for {_dt} "
                    f"(EV +{p['ev_contribution']:.1f})")
        path_summary = "; ".join(_ptxt(i, p) for i, p in enumerate(paths))
        a(f"- Paths ({r['n_paths'] or len(paths)}): {path_summary}")
    elif m == "median":
        a(f"- Primary mechanism: none — median-only valuation "
          f"(no live catalyst: nobody ahead on the depth chart, no material "
          f"role growth, no sidelined teammate vacating targets)")
    else:
        a(f"- Primary mechanism: {m}"
          + (f" (secondary: {r['secondary_mechanism']})" if r["secondary_mechanism"] else ""))
    a(f"- Current role trend: {r['role_trend']}")
    a(f"- Acquisition risk: {fmt_pct(r['acquisition_risk'])} chance he's not practically "
      f"available after the breakout signal")
    a(f"- Value of rostering now vs waiting: +{float(r['now_wait_premium']):.1f} VORP "
      f"(own-now EV +{float(r['owned_option_ev']):.1f} vs wait EV +{float(r['wait_ev']):.1f}; "
      f"FAAB shadow cost −{float(cj.get('faab_cost') or 0):.1f})")
    itv = r["implied_trade_value"]
    ctv = r["chart_trade_value"]
    etv = r["lottery_edge_tv"]
    a(f"- Lottery-implied trade value: **{itv}** "
      f"(chart value {ctv} + lottery edge {etv} — the model's incremental "
      f"value over the role-change expectation the chart already prices)")
    a(f"- Confidence: {r['confidence']} (80% OAV range: "
      f"{float(r['ci_low'] or 0):.1f} to {float(r['ci_high'] or 0):.1f})"
      + (" · ⚠️ bad-variance flag: scoring outran routes"
         if r["bad_variance_flag"] else ""))
    a("")
    text = ej.get("text", "")
    text = re.sub(r"^Ranks #\d+", f"Ranks #{rank}", text)
    a(f"> {text}")
    a("")
    return lines


def row_json(rank, r):
    cj = r["component_json"] or {}
    return {
        "rank": rank, "player": r["player_name"], "pos": r["position"],
        "team": r["team"], "lottery_score": float(r["lottery_score"] or 0),
        "implied_trade_value": r["implied_trade_value"],
        "chart_trade_value": r["chart_trade_value"],
        "lottery_edge_tv": r["lottery_edge_tv"],
        "status": r["status"] or "Healthy",
        "status_detail": r["status_detail"],
        "availability_tier": r["availability_tier"],
        "roster_pct": r["roster_pct"],
        "p1": float(r["p1"] or 0), "p2": float(r["p2"] or 0),
        "p4": float(r["p4"] or 0), "p6": float(r["p6"] or 0),
        "cond_points_pg": float(r["cond_points_pg"] or 0),
        "cond_vorp_pg": float(r["cond_vorp_pg"] or 0),
        "hit_state": (cj.get("hit_state") or
                      ((cj.get("paths") or [{}])[0].get("hit_state"))),
        "hit_window": r["hit_window"],
        "hit_week_lo": r["hit_week_lo"], "hit_week_hi": r["hit_week_hi"],
        "duration_exp": float(r["duration_games"] or 0),
        "duration_lo": float(r["duration_lo"] or 0),
        "duration_hi": float(r["duration_hi"] or 0),
        "paths": cj.get("paths") or [],
        "two_paths": bool(r.get("two_paths")),
        "n_paths": r.get("n_paths") or len(cj.get("paths") or []),
        "primary_mechanism": r["primary_mechanism"],
        "role_trend": r["role_trend"],
        "starter_name": r.get("starter_name"),
        "starter_injury_profile": cj.get("starter_injury_profile"),
        "starter_injury_sentence": cj.get("starter_injury_sentence"),
        "confirm_lag_games": (cj.get("confirm_lag_games")),
        "startability": cj.get("startability"),
        "contingent_injury_mix": cj.get("contingent_injury_mix"),
        "acquisition_risk": float(r["acquisition_risk"] or 0),
        "now_wait_premium": float(r["now_wait_premium"] or 0),
        "confidence": r["confidence"],
        "bad_variance_flag": bool(r["bad_variance_flag"]),
        "explanation": (r["explanation_json"] or {}).get("text"),
    }


def main():
    as_of = latest_as_of()
    rows = board_at(as_of)
    print(f"rendering {len(rows)} rows (as_of {as_of})", flush=True)
    avail = [r for r in rows if r["availability_tier"] == "available"][:N_TICKETS]
    owned = [r for r in rows if r["availability_tier"] == "likely-owned"][:N_STASHES]
    unknown = [r for r in rows if r["availability_tier"] == "unknown"]

    lines = []
    a = lines.append
    a("# Waiver-wire lottery board — %s (v0 heuristic)" % board_week_label())
    a("")
    a(f"_As of {datetime.now(timezone.utc).date()} · 12-team full-PPR, "
      f"1QB/2RB/3WR/1TE/1FLEX, 6 bench · model lottery_v0_heuristic v0.1 · "
      f"{len(rows)} candidates scored_")
    a("")
    a("**How availability is determined:** ESPN %ROST — the share of ESPN "
      "leagues rostering each player, from ESPN's public fantasy API "
      "(true observed ownership, not a proxy). Tiers for a typical 12-team "
      "league: **available** = ROST% < 50 · **unknown** = 50–70 · "
      "**likely-owned** = ROST% ≥ 70. Players missing from ESPN pages fall back "
      "to an ECR-rank + Sleeper-trending composite (confidence Low).")
    a("")
    a("**Lottery Value scale:** 10 = best option-adjusted VORP on this week's "
      "board (week-relative); linear in expected VORP. **Lottery-implied trade "
      "value** is shown as chart value + lottery edge: the chart already prices the "
      "consensus role-change expectation, so only the model's incremental "
      "edge over that consensus is added (never marked down).")
    a("")
    a("**Status:** 🏥 IR/PUP = stash, not a plug-and-play add (still scored — "
      "the role can clear while he's out). ⚠️ = game designation / inactive.")
    a("")
    a("**Caveats:** 2026 route charting is not yet published by nflverse, so "
      "all route/target-share features are 2025 late-season based (flagged "
      "stale). Weeks 1-2 are in the books (MNF pending at render time); "
      "snap/usage features now draw on 2026 games. Depth-chart ranks are ECR-implied, with manual corrections "
      "where a verified depth chart contradicts the implied order "
      "(data/depth_chart_overrides.json). Scores are provisional "
      "until the trained v1 model lands.")
    a("")
    a("**Reading the board:** an 'emergent' path only exists when the role "
      "trend points at a *material* destination (roughly: a 10+ point share "
      "gain toward a full-time role) — small drifts are noise, not paths. "
      "A hit labeled *marginal role gain* means the conditional scoring sits "
      "below the breakout bar for the position (RB 10 / WR 11 / TE 9 PPR/g): "
      "a bigger role that still may not start for you.")
    a("")
    a("---")
    a("")
    a(f"## Lottery tickets — plausibly available on waivers (top {N_TICKETS})")
    a("")
    a("_Ranked by Lottery Value. These are the actual waiver-wire targets._")
    a("")
    for i, r in enumerate(avail, 1):
        lines += player_block(i, r)
    a("---")
    a("")
    a(f"## Upside stashes — likely owned, real upside (top {N_STASHES})")
    a("")
    a("_Not waiver targets in a typical league (ROST% ≥ 70). Monitor list / "
      "buy-low candidates — the option value is real, but you'd have to trade "
      "for them._")
    a("")
    for i, r in enumerate(owned, 1):
        lines += player_block(i, r)
    if unknown:
        a("---")
        a("")
        a("## On the radar — availability unclear")
        a("")
        for r in unknown:
            paths = (r.get("component_json") or {}).get("paths") or []
            leadm = paths[0]["mechanism"] if paths else r["primary_mechanism"]
            a(f"- {r['player_name']} ({r['position']}, {r['team']}) — "
              f"Lottery Value {float(r['lottery_score']):.1f}, "
              f"FP roster {r['roster_pct'] if r['roster_pct'] is not None else 'n/a'}%, "
              f"P4 {fmt_pct(r['p4'])}, {leadm}"
              + (" ⚡ two ways to win" if r.get("two_paths") else "")
              + (f" 🏥{r['status']}" if (r["status"] or "Healthy") != "Healthy" else ""))
        a("")

    md_path = os.path.join(LOT, "results", board_stem() + ".md")
    with open(md_path, "w") as fh:
        fh.write("\n".join(lines))
    print("wrote", md_path, flush=True)

    payload = {
        "as_of": str(as_of)[:10],
        "model": "lottery_v0_heuristic v0.1",
        "league": "12-team full-PPR, 1QB/2RB/3WR/1TE/1FLEX, 6 bench",
        "n_candidates": len(rows),
        "lottery_tickets": [row_json(i, r) for i, r in enumerate(avail, 1)],
        "upside_stashes": [row_json(i, r) for i, r in enumerate(owned, 1)],
        "on_the_radar": [row_json(i, r) for i, r in enumerate(unknown, 1)],
    }
    json_path = os.path.join(LOT, "results", board_stem() + ".json")
    with open(json_path, "w") as fh:
        json.dump(payload, fh, indent=1)
    print("wrote", json_path, flush=True)
    print(f"sections: {len(avail)} tickets / {len(owned)} stashes / "
          f"{len(unknown)} radar", flush=True)


if __name__ == "__main__":
    main()
