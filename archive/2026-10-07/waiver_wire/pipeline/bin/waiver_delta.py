"""Waiver-delta layer: week-over-week VIABILITY-TIER movement.

User spec (2026-09-14): "Waiver value has to be tied to the change in moving
up the board, into a bench or starter viable position, or at least a lottery
ticket."

MONDAY-SAFE RULE (see AGENTS.md): this layer must be computable on Mondays
without fresh expert ECR. Experts don't publish on Mondays, and the chart's
ECR snapshot only refreshes on the Wednesday loop. Therefore:
  - Tier inputs are the lottery board's OWN absolute, week-comparable
    economics: now_wait_premium (total-season VORP of owning now vs waiting),
    cond_vorp_pg (hit-state VORP/game over the waiver line), live paths and
    their p4. All are model outputs / game-stat driven, ECR-refresh-free.
  - NEVER use lottery_score for deltas (week-relative: 10 = max OAV on the
    board; a score can fall while absolute value rises).
  - NEVER use chart_trade_value / implied_trade_value / lottery_edge_tv for
    Monday deltas (the chart leg prices the ECR snapshot, currently
    2026-09-11; its repricing is Wednesday-only).
  - The tier BARS below are structural (roster-model geometry on the frozen
    ECR snapshot both boards share). They are refreshed with the Wednesday
    ECR snapshot, never on Monday.

VIABILITY TIERS (league-agnostic; 12-team 1QB/2RB/3WR/1TE/1FLEX + 6 bench,
same roster model as engine/score_v0.py and the chart):
  starter_viable -- his realistic hit state is a fantasy starter and the
      path is live: cond_vorp_pg >= STARTER_VORP_BAR[pos] and p4 >= 0.10.
      (For a wire stash this is "starter-in-waiting": the achievable role
      is starter-quality, not a median projection.)
  bench_viable   -- worth a bench slot on upside or sheer option value:
      (cond_vorp_pg >= 1.5 with >=1 live path) or (now_wait_premium >= 3.0).
  lottery_ticket -- a real option, not yet roster-worthy on value:
      >=1 live path and now_wait_premium >= 0.5.
  not_rosterable -- none of the above (no live path, or premium < 0.5).

Threshold rationale (documented, not tuned to any player):
  - P4_LIVE = 0.10: path must have >=10% chance of hitting within 4 weeks
    to count as "live enough to matter" for the starter tier.
  - COND_BENCH_BAR = 1.5 VORP/g: hit state must beat the waiver line by a
    material role (noise is ~0.3-0.5/g per the materiality rule).
  - PREMIUM_BENCH_BAR = 3.0 total VORP: own-now option value worth roughly
    a quality spot-start; below that it's stash-not-bench value.
  - PREMIUM_TICKET_FLOOR = 0.5 total VORP: below this the "option" is
    indistinguishable from churn noise.

STARTER_VORP_BAR (VORP/game over the waiver line cleared by the last
positional starter). Derived 2026-09-14 by replicating
engine/score_v0.py::replacement_levels() on the frozen 2026-09-11 ECR
snapshot (the same snapshot both compared boards use):
  RB: starter ppg 11.48 (last of 24) - waiver ppg 4.64 (rank 60) = 6.84
  WR: starter ppg 10.75 (last of 36) - waiver ppg 6.23 (rank 72) = 4.52
  TE: starter ppg  9.87 (last of 12) - waiver ppg 8.79 (rank 18) = 1.08
(QBs are not scored by the lottery model; no QB bar.)

WAIVER_VALUE scoring:
  primary   = (tier_level[cur] - tier_level[prev]) * 2.0 per level crossed
              (up-crossings positive, down-crossings negative)
  secondary = 0.3 * delta_premium, capped at +/-1.0  (within-tier drift)
  new-to-board players: prev tier = not_rosterable, prev premium = 0.0,
      flagged new_ticket.
  dropped-off-board players: cur tier = not_rosterable, cur premium = 0.0,
      flagged dropped.
  Rank delta is recorded but NOT scored (rank inherits lottery_score's
  week-relative normalization).

BEHAVIORAL OVERLAY (Sleeper roster% delta) is CONFIRMATION ONLY, never the
driver: it can agree with or diverge from the model move, never cause one.

Inputs : lottery/results/<board_stem>.json (current) and the most
         recent lottery/results/waiver_board_prev_*.json (prior).
Outputs: lottery/results/<delta_stem>.json (machine-readable, incl.
         top-level "droppable" list)
         lottery/results/<delta_stem>.md  (movers + droppable sections)
         + the movers section is (idempotently) written into
         lottery/results/<board_stem>.md between markers.
         (Board week label + filenames derive from bin/board_week.py —
         never hardcoded.)

BECAME DROPPABLE: a player is flagged droppable when he crosses DOWN into
not_rosterable (automatic), or when an already-not_rosterable player suffers
a MATERIAL absolute premium collapse (>= DROPPABLE_COLLAPSE). Each droppable
record carries prior/current tier, option_value_surrendered (the absolute
premium given up), and what_died (which live paths died / why). Drift of
hundredths of a point never qualifies.
"""
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parent.parent  # waiver_wire/pipeline
sys.path.insert(0, str(_PIPELINE / "bin"))
from board_week import board_stem, delta_stem  # noqa: E402

LOT = str(Path(__file__).resolve().parent.parent)  # waiver_wire/pipeline
RES = os.path.join(LOT, "results")
CUR_FILE = os.path.join(RES, board_stem() + ".json")
PRV_FILE = os.path.join(RES, "waiver_board_prev_2026-09-13.json")
OUT_JSON = os.path.join(RES, delta_stem() + ".json")
OUT_MD = os.path.join(RES, delta_stem() + ".md")
BOARD_MD = os.path.join(RES, board_stem() + ".md")


def resolve_prior():
    """Most recent waiver_board_prev_*.json; falls back to PRV_FILE."""
    import glob
    cands = sorted(glob.glob(os.path.join(RES, "waiver_board_prev_*.json")))
    return cands[-1] if cands else PRV_FILE

# --- thresholds (see header for rationale) ---------------------------------
STARTER_VORP_BAR = {"RB": 6.84, "WR": 4.52, "TE": 1.08}  # as_of ECR 2026-09-11
BARS_AS_OF = "2026-09-11"
P4_LIVE = 0.10
COND_BENCH_BAR = 1.5
PREMIUM_BENCH_BAR = 3.0
PREMIUM_TICKET_FLOOR = 0.5
# DROPPABLE_COLLAPSE: absolute premium collapse that marks an already-
# not_rosterable player as "became droppable". Hundredths-of-a-point drift
# (Boston/Boutte noise) must never qualify — the drop has to be material.
DROPPABLE_COLLAPSE = 0.5
TIER_LEVEL = {"not_rosterable": 0, "lottery_ticket": 1,
              "bench_viable": 2, "starter_viable": 3}
TRANSITION_PTS = 2.0
PREMIUM_SCALE = 0.3
SECONDARY_CAP = 1.0

MD_START = "<!-- WAIVER-DELTA-START -->"
MD_END = "<!-- WAIVER-DELTA-END -->"


def norm_name(s):
    s = (s or "").lower().strip()
    s = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", s)
    s = re.sub(r"[^a-z '\-]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def tier_of(p):
    """Viability tier from the board's absolute economics (header spec)."""
    paths = p.get("paths") or []
    live = [x for x in paths if x.get("mechanism") != "median"]
    prem = float(p.get("now_wait_premium") or 0)
    condv = float(p.get("cond_vorp_pg") or 0)
    p4 = float(p.get("p4") or 0)
    bar = STARTER_VORP_BAR.get(p.get("pos"))
    if bar is not None and live and condv >= bar and p4 >= P4_LIVE:
        return "starter_viable"
    if (live and condv >= COND_BENCH_BAR) or prem >= PREMIUM_BENCH_BAR:
        return "bench_viable"
    if live and prem >= PREMIUM_TICKET_FLOOR:
        return "lottery_ticket"
    return "not_rosterable"


def load_board(path):
    with open(path) as f:
        b = json.load(f)
    out = {}
    for sec in ("lottery_tickets", "upside_stashes", "on_the_radar"):
        for p in b.get(sec, []):
            out[norm_name(p["player"])] = p
    return b.get("as_of"), out


def behavioral_note(d_roster, wv):
    if d_roster is None:
        return "no_signal"
    if wv > 0.5 and d_roster > 1.0:
        return "market_confirms"
    if wv < -0.5 and d_roster < -1.0:
        return "market_confirms"
    if wv > 0.5 and d_roster < -2.0:
        return "market_diverges"
    if wv < -0.5 and d_roster > 2.0:
        return "market_diverges"
    return "no_signal"


def why_line(name, prev, cur, pt, ct, d_prem, wv):
    """One-line model-grounded why for a mover."""
    def best_path(p):
        live = [x for x in (p.get("paths") or [])
                if x.get("mechanism") != "median"]
        if not live:
            return None
        return max(live, key=lambda x: float(x.get("p4") or 0))
    mech = ""
    bp = best_path(cur) if cur else None
    if bp:
        mech = (f"{bp.get('mechanism')} path P4 {float(bp.get('p4') or 0):.1%}, "
                f"cond {float(cur.get('cond_points_pg') or 0):.1f} PPR/g")
    else:
        bp = best_path(prev) if prev else None
        if bp:
            mech = (f"was {bp.get('mechanism')} P4 "
                    f"{float(bp.get('p4') or 0):.1%}")
    if pt != ct:
        return (f"{pt} -> {ct} ({mech}); premium "
                f"{float(prev.get('now_wait_premium') or 0) if prev else 0:.2f}"
                f" -> {float(cur.get('now_wait_premium') or 0) if cur else 0:.2f}")
    return (f"stays {ct} ({mech}); premium "
            f"{d_prem:+.2f} within tier")


def live_mechs(p):
    """Live (non-median) path mechanisms on a board row."""
    if not p:
        return []
    return [x.get("mechanism") for x in (p.get("paths") or [])
            if x.get("mechanism") != "median"]


def droppable_status(p, c, pt, ct, prem_p, prem_c):
    """(is_droppable, option_value_surrendered, what_died).

    Crossed-down players (were rosterable, now not_rosterable) qualify
    automatically. Already-not_rosterable players qualify only on a MATERIAL
    absolute premium collapse (>= DROPPABLE_COLLAPSE) — hundredths-of-a-point
    drift is noise, not a drop.
    """
    crossed_down = (pt != "not_rosterable" and ct == "not_rosterable")
    material_collapse = (pt == "not_rosterable" and ct == "not_rosterable"
                         and (prem_p - prem_c) >= DROPPABLE_COLLAPSE
                         and prem_c < PREMIUM_TICKET_FLOOR)
    if not (crossed_down or material_collapse):
        return False, 0.0, ""
    surrendered = round(max(0.0, prem_p - prem_c), 2)
    died = [m for m in live_mechs(p) if m not in live_mechs(c)]
    died_s = ", ".join(died) if died else "no live path left"
    if c is None:
        what = (f"off the board (was {pt}); live path(s) died: {died_s}; "
                f"premium {prem_p:.2f} -> 0.00")
    elif crossed_down:
        what = (f"{pt} -> {ct}; live path(s) died: {died_s}; "
                f"premium {prem_p:.2f} -> {prem_c:.2f}")
    else:
        what = (f"stayed {ct} but option value collapsed "
                f"{prem_p:.2f} -> {prem_c:.2f}; {died_s}")
    return True, surrendered, what


def main():
    prv_file = resolve_prior()
    as_of_cur, cur = load_board(CUR_FILE)
    as_of_prv, prv = load_board(prv_file)
    names = sorted(set(cur) | set(prv))
    recs = []
    for key in names:
        c, p = cur.get(key), prv.get(key)
        base = c or p
        ct = tier_of(c) if c else "not_rosterable"
        pt = tier_of(p) if p else "not_rosterable"
        prem_c = float((c or {}).get("now_wait_premium") or 0)
        prem_p = float((p or {}).get("now_wait_premium") or 0)
        d_prem = prem_c - prem_p
        trans = (TIER_LEVEL[ct] - TIER_LEVEL[pt]) * TRANSITION_PTS
        sec = max(-SECONDARY_CAP, min(SECONDARY_CAP, PREMIUM_SCALE * d_prem))
        wv = round(trans + sec, 2)
        rc = (c or {}).get("roster_pct")
        rp = (p or {}).get("roster_pct")
        d_roster = (rc - rp) if (rc is not None and rp is not None) else None
        is_drop, surrendered, what_died = droppable_status(
            p, c, pt, ct, prem_p, prem_c)
        rec = {
            "player": base["player"], "pos": base["pos"], "team": base["team"],
            "tier_prev": pt, "tier_cur": ct,
            "tier_transition": f"{pt}->{ct}" if pt != ct else "none",
            "premium_prev": round(prem_p, 2), "premium_cur": round(prem_c, 2),
            "delta_premium": round(d_prem, 2),
            "rank_prev": (p or {}).get("rank"), "rank_cur": (c or {}).get("rank"),
            "delta_rank": ((p or {}).get("rank") - (c or {}).get("rank"))
                         if (p and c and p.get("rank") and c.get("rank")) else None,
            "delta_roster_pct": round(d_roster, 1) if d_roster is not None else None,
            "behavioral": behavioral_note(d_roster, wv),
            "new_ticket": c is not None and p is None,
            "dropped": p is not None and c is None,
            "waiver_value": wv,
            "why": why_line(base["player"], p, c, pt, ct, d_prem, wv),
            "droppable": is_drop,
            "option_value_surrendered": surrendered,
            "what_died": what_died,
        }
        recs.append(rec)

    movers_up = sorted([r for r in recs if r["waiver_value"] > 0],
                       key=lambda r: -r["waiver_value"])
    movers_dn = sorted([r for r in recs if r["waiver_value"] < 0],
                       key=lambda r: r["waiver_value"])
    droppable = sorted([r for r in recs if r["droppable"]],
                       key=lambda r: -r["option_value_surrendered"])
    summary = {
        "n_up": len(movers_up), "n_down": len(movers_dn),
        "n_flat": len(recs) - len(movers_up) - len(movers_dn),
        "n_droppable": len(droppable),
    }

    out = {
        "as_of": date.today().isoformat(),
        "board_current_as_of": as_of_cur, "board_prior_as_of": as_of_prv,
        "monday_safe": True,
        "notes": ("Tiers from board absolute economics only "
                  "(now_wait_premium, cond_vorp_pg, live paths/p4). "
                  "lottery_score and chart legs excluded by design."),
        "bars": {"starter_vorp_bar": STARTER_VORP_BAR, "bars_as_of": BARS_AS_OF,
                 "p4_live": P4_LIVE, "cond_bench_bar": COND_BENCH_BAR,
                 "premium_bench_bar": PREMIUM_BENCH_BAR,
                 "premium_ticket_floor": PREMIUM_TICKET_FLOOR,
                 "transition_pts_per_level": TRANSITION_PTS,
                 "premium_scale": PREMIUM_SCALE, "secondary_cap": SECONDARY_CAP},
        "summary": summary,
        "droppable": [
            {"player": r["player"], "pos": r["pos"], "team": r["team"],
             "tier_prev": r["tier_prev"], "tier_cur": r["tier_cur"],
             "premium_prev": r["premium_prev"], "premium_cur": r["premium_cur"],
             "option_value_surrendered": r["option_value_surrendered"],
             "what_died": r["what_died"],
             "dropped_off_board": r["dropped"]}
            for r in droppable
        ],
        "players": sorted(recs, key=lambda r: -r["waiver_value"]),
    }
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=1)

    # ---- readable movers section -----------------------------------------
    L = []
    A = L.append
    A("# Waiver delta — tier movement week over week")
    A("")
    A(f"Current board {as_of_cur} vs prior {as_of_prv}. "
      f"{summary['n_up']} up, {summary['n_down']} down, "
      f"{summary['n_flat']} flat. Monday-safe: no ECR input; tiers from the "
      f"board's own absolute economics (premium / cond VORP / live paths). "
      f"Starter bars (VORP/g over waiver line, ECR {BARS_AS_OF}): "
      + ", ".join(f"{k} {v}" for k, v in STARTER_VORP_BAR.items()) + ".")
    A("")
    A("## Top upward movers")
    A("")
    for r in movers_up[:8]:
        tag = " 🆕 new" if r["new_ticket"] else ""
        A(f"- **{r['player']}** ({r['pos']}, {r['team']}) "
          f"waiver_value {r['waiver_value']:+.2f}{tag}: {r['why']} "
          f"[behavioral: {r['behavioral']}]")
    if not movers_up:
        A("- none")
    A("")
    A("## Top downward movers")
    A("")
    for r in movers_dn[:8]:
        tag = " 📤 off board" if r["dropped"] else ""
        A(f"- **{r['player']}** ({r['pos']}, {r['team']}) "
          f"waiver_value {r['waiver_value']:+.2f}{tag}: {r['why']} "
          f"[behavioral: {r['behavioral']}]")
    if not movers_dn:
        A("- none")
    A("")
    A("## Became droppable")
    A("")
    A("Crossed down into not_rosterable, or suffered a material (>= "
      f"{DROPPABLE_COLLAPSE} premium) collapse while already not_rosterable. "
      "Hundredths-of-a-point drift is noise and never qualifies.")
    A("")
    for r in droppable:
        tag = " 📤 off board" if r["dropped"] else ""
        A(f"- **{r['player']}** ({r['pos']}, {r['team']}){tag}: "
          f"{r['tier_prev']} -> {r['tier_cur']}; "
          f"option value surrendered {r['option_value_surrendered']:.2f} "
          f"(premium {r['premium_prev']:.2f} -> {r['premium_cur']:.2f}). "
          f"What died: {r['what_died']}")
    if not droppable:
        A("- none")
    A("")
    A("## Method note")
    A("")
    A("Tier = current roster-worthiness state (starter_viable / bench_viable / "
      "lottery_ticket / not_rosterable). waiver_value = 2.0 per tier level "
      "crossed + 0.3 x delta_premium (capped +/-1.0). Rank delta is shown but "
      "never scored (rank inherits lottery_score's week-relative scale). "
      "Sleeper roster% delta is confirmation only, never the driver.")
    md = "\n".join(L) + "\n"
    with open(OUT_MD, "w") as f:
        f.write(md)

    # ---- wire into the board .md (idempotent, marker-delimited) -----------
    section = f"{MD_START}\n{md}{MD_END}\n"
    with open(BOARD_MD) as f:
        board_md = f.read()
    if MD_START in board_md:
        pre = board_md.split(MD_START)[0]
        post = board_md.split(MD_END)[1] if MD_END in board_md else ""
        board_md = pre + section + post.lstrip("\n")
    else:
        board_md = board_md.rstrip("\n") + "\n\n" + section
    with open(BOARD_MD, "w") as f:
        f.write(board_md)

    print(f"waiver_delta: {summary['n_up']} up / {summary['n_down']} down / "
          f"{summary['n_flat']} flat / {summary['n_droppable']} droppable "
          f"-> {OUT_JSON}, {OUT_MD}")
    for r in out["players"][:5]:
        print(f"  {r['waiver_value']:+.2f} {r['player']} {r['tier_transition']}")
    for r in out["players"][-3:]:
        if r["waiver_value"] < 0:
            print(f"  {r['waiver_value']:+.2f} {r['player']} {r['tier_transition']}")


if __name__ == "__main__":
    main()
