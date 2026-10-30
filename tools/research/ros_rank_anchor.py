#!/usr/bin/env python3
"""JEG-1198 research: can ROS rankings imply trade values on the published scale?

Research only. Reads:
  - published DDF Values (12 teams, 1QB) for ppr/half_ppr/standard, copied from the DDF
    connector get_values on 2026-10-29 01:3x UTC (as_of 2026-10-28)  -> published_<s>.txt
  - data/fixtures/current/players.json (as_of 2026-10-28; ROS weeks 8-18): ESPN, CBS ROS,
    Razzball rest-of-season projections, converted to positional ranks (MODELED ranks)
  - StickToTheModel ROS PPR top-30 per position, page dated 2026-10-20 (STALE: weeks 7-18)
  - data/fixtures/snapshots/players_2026-09-23.json: the earlier ESPN ROS read, for the
    stability comparison (fixture as_of 2026-09-23, its ESPN pull labelled 2026-09-29)
Joins are on canonical player_key (tools/research/ros_rank_keys.py, stored registry
snapshot); players.json rows carry the bake's own player_key. Unresolved names are
reported in the output's "joins" block, never collapsed (JEG-1251).
Writes docs/research/data/jeg1198/ros_rank_study_out.json only. No production math is changed.
"""
import json, re, statistics as st, sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
W = REPO / "docs/research/data/jeg1198"
SCORINGS = ["ppr", "half_ppr", "standard"]
POS = ["QB", "RB", "WR", "TE"]
DEPTH = {"QB": 12, "RB": 30, "WR": 36, "TE": 12}  # comparison depth (about starters + flex)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ros_rank_keys as K  # noqa: E402  canonical player_key joins (JEG-1251)

PLAYERS_PATH = REPO / "data/fixtures/current/players.json"
PRIOR_PATH = REPO / "data/fixtures/snapshots/players_2026-09-23.json"
players = json.load(open(PLAYERS_PATH))["players"]
by_key = {p["player_key"]: p for p in players}

def load_pub(s):
    out = {}
    for line in open(W / f"published_{s}.txt"):
        if not line.strip():
            continue
        name, pos, v = line.strip().split("|")
        K.put(out, name, pos, f"published_{s}", (name, pos, float(v)))
    return out

def spearman(a, b):
    keys = [k for k in a if k in b]
    if len(keys) < 3:
        return None, len(keys)
    def rk(d):
        order = sorted(keys, key=lambda k: d[k])
        return {k: i for i, k in enumerate(order)}
    ra, rb = rk(a), rk(b)
    n = len(keys)
    d2 = sum((ra[k] - rb[k]) ** 2 for k in keys)
    return 1 - 6 * d2 / (n * (n * n - 1)), n

def ranks_from_points(points):  # {key: pts} -> {key: rank 1..}
    order = sorted(points, key=lambda k: -points[k])
    return {k: i + 1 for i, k in enumerate(order)}

def interp_curve(curve, r):
    """curve: published values sorted desc for one position (rank 1 = curve[0]).
    Piecewise-linear in rank for fractional ranks; beyond depth -> None (no anchor)."""
    if r < 1:
        r = 1
    lo = int(r)
    if lo > len(curve):
        return None
    if lo == len(curve) or r == lo:
        return curve[lo - 1]
    f = r - lo
    return curve[lo - 1] * (1 - f) + curve[lo] * f

def ranker_points(s):
    """Modeled ROS points per ranker for one scoring, keyed by the bake's player_key, with pos."""
    R = {"espn": {}, "cbsros": {}, "razzball": {}}
    for p in players:
        if p["pos"] not in POS:
            continue
        k = p["player_key"]
        if p.get("espn_complete") and p.get("espn_ros"):
            R["espn"][k] = (p["pos"], p["espn_ros"][s])
        if p.get("cbsros_complete") and p.get("cbsros_ppg"):
            R["cbsros"][k] = (p["pos"], p["cbsros_ppg"][s] * p["games_remaining"])
        if p.get("rz_complete") and p.get("rz_ros"):
            R["razzball"][k] = (p["pos"], p["rz_ros"][s])
    return R

def sttm_ranks():
    out = {}
    for line in open(W / "sttm_ros_ppr_2026-10-20.txt"):
        if not line.strip():
            continue
        pos, names = line.strip().split("|")
        for i, nm in enumerate(names.split(";")):
            K.put(out, nm, pos, "sttm_ros_ppr_2026-10-20", (pos, i + 1))
    return out

report = {"provenance": {**K.provenance(),
                         "players_json": {"path": str(PLAYERS_PATH.relative_to(REPO)), "sha256": K.sha256(PLAYERS_PATH)},
                         "prior_players_json": {"path": str(PRIOR_PATH.relative_to(REPO)), "sha256": K.sha256(PRIOR_PATH)}},
          "scorings": {}}
for s in SCORINGS:
    pub = load_pub(s)
    curves = {pos: sorted([v for (_, pp, v) in pub.values() if pp == pos], reverse=True) for pos in POS}
    overall_curve = sorted([v for (_, _, v) in pub.values()], reverse=True)
    pubpos = {pos: {k: v for k, (_, pp, v) in pub.items() if pp == pos} for pos in POS}
    pubrank = {pos: ranks_from_points(pubpos[pos]) for pos in POS}
    RP = ranker_points(s)
    rankers = {}
    for name, d in RP.items():
        rankers[name] = {pos: ranks_from_points({k: pts for k, (pp, pts) in d.items() if pp == pos}) for pos in POS}
    if s == "ppr":
        sr = sttm_ranks()
        rankers["sttm_stale"] = {pos: {k: r for k, (pp, r) in sr.items() if pp == pos} for pos in POS}
    res = {"curve_shape": {}, "agreement": {}, "players": {}, "overall_vs_positional": {}}
    # 1. curve shape: gaps between consecutive published ranks are unequal
    for pos in POS:
        c = curves[pos]
        d = DEPTH[pos]
        gaps = [round(c[i] - c[i + 1], 1) for i in range(min(d, len(c) - 1))]
        res["curve_shape"][pos] = {
            "top": c[0], "rank_%d" % (d // 2): c[d // 2 - 1], "rank_%d" % d: c[d - 1] if len(c) >= d else None,
            "gap_1_2": gaps[0], "median_gap_top_depth": st.median(gaps), "max_gap": max(gaps),
            "n_priced_gt0": sum(1 for v in c if v > 0),
        }
    # 2. agreement: Spearman ranker vs published order, and ranker vs ranker, within published top DEPTH
    for pos in POS:
        top = {k: pubrank[pos][k] for k in pubrank[pos] if pubrank[pos][k] <= DEPTH[pos]}
        row = {}
        for rn, rk in rankers.items():
            sub = {k: rk[pos][k] for k in top if k in rk[pos]}
            rho, n = spearman(top, sub)
            row[rn] = {"rho_vs_published": None if rho is None else round(rho, 2), "n": n,
                       "missing_published_top": DEPTH[pos] - n}
        names = list(rankers)
        pair = {}
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a = {k: rankers[names[i]][pos][k] for k in top if k in rankers[names[i]][pos]}
                b = {k: rankers[names[j]][pos][k] for k in top if k in rankers[names[j]][pos]}
                rho, n = spearman(a, b)
                pair[f"{names[i]}~{names[j]}"] = None if rho is None else round(rho, 2)
        res["agreement"][pos] = {"vs_published": row, "pairwise": pair}
    # 3. implied values per player: positional rank-matching per ranker; aggregate two ways
    for pos in POS:
        for k, r_pub in pubrank[pos].items():
            if r_pub > DEPTH[pos]:
                continue
            name = pub[k][0]
            ranks = {rn: rk[pos][k] for rn, rk in rankers.items() if k in rk[pos]}
            implied = {rn: interp_curve(curves[pos], r) for rn, r in ranks.items()}
            implied = {rn: v for rn, v in implied.items() if v is not None}
            cur = [v for rn, v in implied.items() if rn != "sttm_stale"]
            curr_ranks = [r for rn, r in ranks.items() if rn != "sttm_stale"]
            mean_rank = st.mean(curr_ranks) if curr_ranks else None
            res["players"][name] = {
                "pos": pos, "published": pubpos[pos][k], "published_pos_rank": r_pub,
                "ranks": ranks, "implied_by_ranker": {rn: round(v, 1) for rn, v in implied.items()},
                "n_current_rankers": len(cur),
                "implied_mean_of_values": round(st.mean(cur), 1) if cur else None,
                "implied_at_mean_rank": round(interp_curve(curves[pos], mean_rank), 1) if mean_rank else None,
                "implied_at_median_rank": round(interp_curve(curves[pos], st.median(curr_ranks)), 1) if curr_ranks else None,
                "implied_range": [round(min(cur), 1), round(max(cur), 1)] if cur else None,
                "rank_sd": round(st.pstdev(curr_ranks), 1) if len(curr_ranks) > 1 else None,
            }
    # 4. overall (cross-position) rank-matching vs positional, ESPN points, for scarcity check
    allpts = {k: pts for k, (pp, pts) in RP["espn"].items()}
    orank = ranks_from_points(allpts)
    for pos in POS:
        out = []
        for k, r_pub in sorted(pubrank[pos].items(), key=lambda x: x[1])[:5]:
            if k in orank and k in rankers["espn"][pos]:
                out.append({"player": pub[k][0], "published": pubpos[pos][k],
                            "positional_implied": round(interp_curve(curves[pos], rankers["espn"][pos][k]), 1),
                            "overall_rank": orank[k],
                            "overall_implied": overall_curve[orank[k] - 1] if orank[k] <= len(overall_curve) else None})
        res["overall_vs_positional"][pos] = out
    # 5. thin / missing anchors
    thin = [n for n, d in res["players"].items() if d["n_current_rankers"] < 2]
    res["thin_anchor_players"] = thin
    unpriced = {}
    for rn, rk in rankers.items():
        u = []
        for pos in POS:
            for k, r in rk[pos].items():
                if r <= DEPTH[pos] and (k not in pubpos[pos] or pubpos[pos][k] == 0):
                    u.append(f"{by_key[k]['name'] if k in by_key else k} ({pos}{r})")
        unpriced[rn] = u
    res["ranked_but_unpriced"] = unpriced
    report["scorings"][s] = res

# 6. stability: ESPN ROS ranks in the earlier fixture vs now, joined on player_key.
# Interval: fixture as_of 2026-09-23 (ESPN pull labelled 2026-09-29) to 2026-10-28, i.e.
# 29 to 35 days, one pair of reads. Horizons differ (weeks 4-18 then, 8-18 now). This
# bounds how far ESPN's order moved over that interval only; it is not a weekly rate.
prior = json.load(open(PRIOR_PATH))
prior_by_key = {p["player_key"]: p for p in prior["players"]}
stab = {"interval": {"from_fixture_as_of": prior["meta"]["as_of"], "from_espn_snapshot": prior["meta"].get("espn_snapshot"),
                     "to_fixture_as_of": json.load(open(PLAYERS_PATH))["meta"]["as_of"],
                     "days": "29 to 35 (one pair of reads, not week to week)"},
        "scorings": {}}
for s in SCORINGS:
    pub = load_pub(s)
    curves = {pos: sorted([v for (_, pp, v) in pub.values() if pp == pos], reverse=True) for pos in POS}
    row = {}
    for pos in POS:
        now = {p["player_key"]: p["espn_ros"][s] for p in players
               if p["pos"] == pos and p.get("espn_complete") and p.get("espn_ros")}
        then = {k: q["espn_ros"][s] for k, q in prior_by_key.items()
                if q.get("pos") == pos and q.get("espn_complete") and q.get("espn_ros")}
        rnow, rthen = ranks_from_points(now), ranks_from_points(then)
        top = [k for k, r in rnow.items() if r <= DEPTH[pos]]
        both = [k for k in top if k in rthen]
        rho, n = spearman({k: rnow[k] for k in both}, {k: rthen[k] for k in both})
        moves = [abs(rnow[k] - rthen[k]) for k in both]
        pts = [abs((interp_curve(curves[pos], rnow[k]) or 0) - (interp_curve(curves[pos], rthen[k]) or 0)) for k in both]
        row[pos] = {"n_now_top": len(top), "n_joined": n, "missing_then": [by_key[k]["name"] for k in top if k not in rthen],
                    "spearman": None if rho is None else round(rho, 2),
                    "median_rank_move": st.median(moves) if moves else None,
                    "median_points_on_today_curve": round(st.median(pts), 1) if pts else None}
    stab["scorings"][s] = row
report["stability_espn"] = stab
report["joins"] = K.join_report()

json.dump(report, open(W / "ros_rank_study_out.json", "w"), indent=1)

# Console summary
for s in SCORINGS:
    r = report["scorings"][s]
    print(f"\n===== {s} =====")
    for pos in POS:
        print(pos, "curve", r["curve_shape"][pos])
    for pos in POS:
        print(pos, "rho vs published", {k: v["rho_vs_published"] for k, v in r["agreement"][pos]["vs_published"].items()},
              "pairwise", r["agreement"][pos]["pairwise"])
    for pos in POS:
        print(pos, "overall vs positional", r["overall_vs_positional"][pos])
    div = []
    for n, d in r["players"].items():
        imp = d["implied_mean_of_values"]
        if imp is None:
            continue
        diff = imp - d["published"]
        pct = diff / d["published"] if d["published"] else 0
        if abs(diff) > 2 and abs(pct) > 0.05:
            div.append((round(diff, 1), n, d["pos"], d["published"], imp, d["implied_range"], d["ranks"]))
    div.sort(key=lambda x: -abs(x[0]))
    print("material divergences (>5% and >2 pts):", len(div), "of", sum(1 for d in r["players"].values() if d["implied_mean_of_values"] is not None))
    for x in div[:14]:
        print("  ", x)
    print("thin anchors:", r["thin_anchor_players"])
    print("ranked but unpriced:", {k: v for k, v in r["ranked_but_unpriced"].items()})
print("\n===== stability (ESPN, player_key join) =====")
print(json.dumps(report["stability_espn"]["interval"]))
for s in SCORINGS:
    print(s, {pos: {k: v for k, v in d.items() if k != "missing_then"} for pos, d in report["stability_espn"]["scorings"][s].items()})
print("\n===== joins =====")
for lid, j in report["joins"].items():
    print(lid, j["counts"], [f"{x['name']} {x['pos']} {x['reason']}" for x in j["not_joined"]])
