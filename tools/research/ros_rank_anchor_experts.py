#!/usr/bin/env python3
"""JEG-1198 rerun (option C): the same rank-to-value test on real expert ROS rankings.

Research only. Reads, besides the published values of the first study (published_<s>.txt):
  - roslist_2026-10-29.txt: the two feeds pipelines/pull_ros_rankings.py read on a runner
    on 2026-10-29 (dry run 40802150829), copied to study depth:
      fantasypros_ros_ecr  expert consensus (6 experts), Half PPR, updated 2026-10-28
      yahoo_pianowski_ros  Scott Pianowski's dollar tiers, scoring unstated; one article per
                           position: QB 2026-09-30, TE 10-07, RB 10-14, WR 10-21 (QB and TE stale)
  - espn_ros_karabell_2026-10-27.txt: ESPN's ROS article (Eric Karabell, 2026-10-27, scoring
    unstated), read once on 2026-10-29 for this study. Not piped: a runner gets HTTP 202.
  - data/fixtures/current/players.json: the modeled ranks of the first study (ESPN, CBS ROS,
    Razzball projections), for expert-vs-model agreement.
Pianowski ranks are by dollar value, ties sharing the average rank (he treats equal salaries
as even); his injury tier is placed by value too. Joins are on canonical player_key
(tools/research/ros_rank_keys.py); unresolved names are reported in the output's "joins"
block, never collapsed (JEG-1251). Writes ros_rank_experts_out.json only.
"""
import json
import statistics as st
import sys
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
W = REPO / "docs/research/data/jeg1198"
SCORINGS = ["ppr", "half_ppr", "standard"]
POS = ["QB", "RB", "WR", "TE"]
DEPTH = {"QB": 12, "RB": 30, "WR": 36, "TE": 12}
EXPERTS = ["ecr_consensus", "yahoo_pianowski", "espn_karabell"]
MODELED = ["espn_proj", "cbsros_proj", "razzball_proj"]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ros_rank_keys as K  # noqa: E402  canonical player_key joins (JEG-1251)


def load_pub(s):
    out = {}
    for line in open(W / f"published_{s}.txt"):
        if line.strip():
            name, pos, v = line.strip().split("|")
            K.put(out, name, pos, f"published_{s}", (name, pos, float(v)))
    return out


def ranks_by_value(items):
    """[(key, value)] -> {key: rank}, higher value first, ties share the average rank."""
    items = sorted(items, key=lambda x: -x[1])
    out, i = {}, 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][1] == items[i][1]:
            j += 1
        for k, _ in items[i:j + 1]:
            out[k] = (i + 1 + j + 1) / 2
        i = j + 1
    return out


def load_experts():
    R = {e: {p: {} for p in POS} for e in EXPERTS}
    yahoo = {p: [] for p in POS}
    vint = {}
    for line in open(W / "roslist_2026-10-29.txt"):
        if not line.strip():
            continue
        _, src, scoring, pos, vintage, body = line.strip().split("|", 5)
        vint[f"{src}:{pos}"] = {"vintage": vintage, "scoring": scoring}
        for item in body.split(";"):
            rank, name, value, _tier = item.split(":")
            if src == "fantasypros_ros_ecr":
                K.put(R["ecr_consensus"][pos], name, pos, f"{src}:{scoring}", int(rank))
            else:
                k = K.pk(name, pos, f"{src}:{scoring}")
                if k is not None:
                    yahoo[pos].append((k, float(value)))
    for pos in POS:
        R["yahoo_pianowski"][pos] = ranks_by_value(yahoo[pos])
    for line in open(W / "espn_ros_karabell_2026-10-27.txt"):
        if line.strip():
            pos, names = line.strip().split("|")
            for i, nm in enumerate(names.split(";")):
                K.put(R["espn_karabell"][pos], nm, pos, "espn_ros_karabell_2026-10-27", i + 1)
    vint["espn_karabell"] = {"vintage": "2026-10-27", "scoring": "unstated"}
    return R, vint


def load_modeled(s):
    players = json.load(open(REPO / "data/fixtures/current/players.json"))["players"]
    pts = {m: {p: [] for p in POS} for m in MODELED}
    for p in players:
        if p["pos"] not in POS:
            continue
        k = p["player_key"]  # the bake's canonical key
        if p.get("espn_complete") and p.get("espn_ros"):
            pts["espn_proj"][p["pos"]].append((k, p["espn_ros"][s]))
        if p.get("cbsros_complete") and p.get("cbsros_ppg"):
            pts["cbsros_proj"][p["pos"]].append((k, p["cbsros_ppg"][s] * p["games_remaining"]))
        if p.get("rz_complete") and p.get("rz_ros"):
            pts["razzball_proj"][p["pos"]].append((k, p["rz_ros"][s]))
    return {m: {p: ranks_by_value(pts[m][p]) for p in POS} for m in MODELED}


def spearman(a, b):
    keys = [k for k in a if k in b]
    if len(keys) < 3:
        return None
    ra = ranks_by_value([(k, -a[k]) for k in keys])
    rb = ranks_by_value([(k, -b[k]) for k in keys])
    ma, mb = st.mean(ra.values()), st.mean(rb.values())
    num = sum((ra[k] - ma) * (rb[k] - mb) for k in keys)
    den = (sum((ra[k] - ma) ** 2 for k in keys) * sum((rb[k] - mb) ** 2 for k in keys)) ** 0.5
    return round(num / den, 2) if den else None


def interp(curve, r):
    r = max(r, 1)
    lo = int(r)
    if lo > len(curve):
        return None
    if lo == len(curve) or r == lo:
        return curve[lo - 1]
    f = r - lo
    return curve[lo - 1] * (1 - f) + curve[lo] * f


def material(diff, pub):
    return abs(diff) > 2 and pub and abs(diff / pub) > 0.05


EXPERT_R, VINTAGES = load_experts()
report = {"provenance": K.provenance(), "vintages": VINTAGES, "scorings": {}}
for s in SCORINGS:
    pub = load_pub(s)
    curves = {p: sorted([v for (_, pp, v) in pub.values() if pp == p], reverse=True) for p in POS}
    pubpos = {p: {k: v for k, (_, pp, v) in pub.items() if pp == p} for p in POS}
    pubrank = {p: ranks_by_value(list(pubpos[p].items())) for p in POS}
    rankers = {**EXPERT_R, **load_modeled(s)}
    res = {"agreement": {}, "players": {}, "summary": {}}
    for p in POS:
        top = {k: r for k, r in pubrank[p].items() if r <= DEPTH[p]}
        vs_pub = {rn: spearman(top, {k: rankers[rn][p][k] for k in top if k in rankers[rn][p]}) for rn in rankers}
        cover = {rn: sum(1 for k in top if k in rankers[rn][p]) for rn in EXPERTS}
        pair = {}
        names = list(rankers)
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a = {k: rankers[names[i]][p][k] for k in top if k in rankers[names[i]][p]}
                b = {k: rankers[names[j]][p][k] for k in top if k in rankers[names[j]][p]}
                pair[f"{names[i]}~{names[j]}"] = spearman(a, b)
        res["agreement"][p] = {"vs_published": vs_pub, "expert_coverage_of_top": cover, "pairwise": pair}
        for k, rp in top.items():
            name = pub[k][0]
            er = {rn: rankers[rn][p][k] for rn in EXPERTS if k in rankers[rn][p]}
            mr = {rn: rankers[rn][p][k] for rn in MODELED if k in rankers[rn][p]}
            ei = {rn: round(interp(curves[p], r), 1) for rn, r in er.items() if interp(curves[p], r) is not None}
            mi = [interp(curves[p], r) for r in mr.values() if interp(curves[p], r) is not None]
            ev = list(ei.values())
            res["players"][name] = {
                "pos": p, "published": pubpos[p][k], "published_pos_rank": rp,
                "expert_ranks": er, "implied_by_expert": ei,
                "implied_experts_mean": round(st.mean(ev), 1) if ev else None,
                "implied_experts_range": [min(ev), max(ev)] if ev else None,
                "implied_modeled_mean": round(st.mean(mi), 1) if mi else None,
                "expert_rank_sd": round(st.pstdev(list(er.values())), 1) if len(er) > 1 else None,
            }
    pl = [d for d in res["players"].values() if d["implied_experts_mean"] is not None]
    div = [d for d in pl if material(d["implied_experts_mean"] - d["published"], d["published"])]
    div_mod = [d for d in pl if d["implied_modeled_mean"] is not None
               and material(d["implied_modeled_mean"] - d["published"], d["published"])]
    by_pos = {p: [abs(d["implied_experts_mean"] - d["published"]) for d in pl if d["pos"] == p] for p in POS}
    res["summary"] = {
        "compared": len(pl), "material_vs_published_experts": len(div),
        "material_vs_published_modeled": len(div_mod),
        "median_abs_gap_experts": {p: round(st.median(v), 1) for p, v in by_pos.items() if v},
        "median_expert_rank_sd": {p: st.median([d["expert_rank_sd"] for d in pl if d["pos"] == p and d["expert_rank_sd"] is not None]) for p in POS},
        "median_expert_range_pts": {p: round(st.median([d["implied_experts_range"][1] - d["implied_experts_range"][0] for d in pl if d["pos"] == p and len(d["implied_by_expert"]) > 1]), 1) for p in POS},
        "largest": sorted(((round(d["implied_experts_mean"] - d["published"], 1), n) for n, d in res["players"].items() if d in div), key=lambda x: -abs(x[0]))[:14],
    }
    report["scorings"][s] = res

report["joins"] = K.join_report()
json.dump(report, open(W / "ros_rank_experts_out.json", "w"), indent=1)
for s in SCORINGS:
    r = report["scorings"][s]
    print(f"\n===== {s} =====")
    for p in POS:
        a = r["agreement"][p]
        print(p, "vs published", a["vs_published"], "coverage", a["expert_coverage_of_top"])
        print("   experts pairwise", {k: v for k, v in a["pairwise"].items() if k.split("~")[0] in EXPERTS and k.split("~")[1] in EXPERTS})
        print("   expert~model", {k: v for k, v in a["pairwise"].items() if (k.split("~")[0] in EXPERTS) != (k.split("~")[1] in EXPERTS)})
    print("summary", json.dumps(r["summary"]))
    for n in ["Chase Brown", "Malik Nabers", "Drake Maye", "Jalen Coker", "Jayden Daniels", "Josh Jacobs", "Kenneth Walker III", "Tony Pollard", "Breece Hall"]:
        d = r["players"].get(n)
        if d:
            print(f"  {n}: pub {d['published']} (#{d['published_pos_rank']}) experts {d['expert_ranks']} -> {d['implied_by_expert']} mean {d['implied_experts_mean']} | modeled mean {d['implied_modeled_mean']}")
