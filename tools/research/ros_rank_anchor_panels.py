#!/usr/bin/env python3
"""JEG-1198 second rerun: the rank-to-value test with the wider ROS source set.

Research only. Jeremy 2026-10-29 asked for "multiple cuts of the fantasypros data" and set
the rule "do not blend weekly data with ROS data, ever": every list here is rest-of-season.

Reads, besides the published values of the first study (published_<s>.txt):
  - roslist_2026-10-29b.txt: what pipelines/pull_ros_rankings.py read on a runner on
    2026-10-29 (dry run 40806312909), each list cut to three times study depth:
      fantasypros_ros_ecr     expert consensus, one list per scoring (Half PPR, PPR, standard)
      fantasypros_expert_ros  each expert's own ROS list, per scoring (21 experts Half PPR,
                              20 PPR and standard); dated by the site's Updated date
      yahoo_pianowski_ros     Scott Pianowski's dollar tiers, scoring unstated
  - espn_ros_karabell_2026-10-27.txt: ESPN's ROS article (scoring unstated), as before.

Double count: the consensus averages a subset of the expert lists, so the two are never
averaged together. Two panels are compared instead, each one analyst one vote:
  consensus panel  = expert consensus + Pianowski + Karabell
  expert panel     = every expert list updated within 14 days + Pianowski + Karabell
Lists older than 14 days are reported but left out of the expert panel.
Joins are on canonical player_key (tools/research/ros_rank_keys.py); unresolved names are
reported in the output's "joins" block, never collapsed (JEG-1251).
Writes ros_rank_panels_out.json only.
"""
import json
import statistics as st
import sys
from datetime import date
from pathlib import Path

REPO = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
W = REPO / "docs/research/data/jeg1198"
SCORINGS = ["ppr", "half_ppr", "standard"]
POS = ["QB", "RB", "WR", "TE"]
DEPTH = {"QB": 12, "RB": 30, "WR": 36, "TE": 12}
STUDY_DAY = date(2026, 10, 29)
STALE_DAYS = 14
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


def load_lists():
    """{scoring: {list_id: {pos: {key: rank}}}} plus list metadata."""
    lists = {s: {} for s in SCORINGS}
    meta = {}
    shared = {}
    for line in open(W / "roslist_2026-10-29b.txt"):
        if not line.strip():
            continue
        _, src, analyst, scoring, pos, vintage, body = line.strip().split("|", 6)
        lid = {"fantasypros_ros_ecr": "consensus", "yahoo_pianowski_ros": "pianowski"}.get(src, analyst)
        age = (STUDY_DAY - date.fromisoformat(vintage)).days
        meta.setdefault(lid, {"source": src, "vintages": {}, "stale": False})
        meta[lid]["vintages"][pos] = vintage
        if src == "fantasypros_expert_ros":
            meta[lid]["stale"] = age > STALE_DAYS
        ranks = {}
        for item in body.split(";"):
            rank, rest = item.split(":", 1)
            name, _value, _tier = rest.rsplit(":", 2)
            K.put(ranks, name, pos, f"{src}:{analyst}:{scoring}", float(rank))
        if scoring == "unstated":
            shared.setdefault(lid, {})[pos] = ranks
        else:
            lists[scoring].setdefault(lid, {})[pos] = ranks
    for line in open(W / "espn_ros_karabell_2026-10-27.txt"):
        if line.strip():
            pos, names = line.strip().split("|")
            kr = {}
            for i, n in enumerate(names.split(";")):
                K.put(kr, n, pos, "espn_ros_karabell_2026-10-27", i + 1)
            shared.setdefault("karabell", {})[pos] = kr
    meta["karabell"] = {"source": "espn_ros_article", "vintages": {p: "2026-10-27" for p in POS}, "stale": False}
    for s in SCORINGS:
        lists[s].update(shared)
    return lists, meta


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


LISTS, META = load_lists()
fresh_experts = sorted(l for l, m in META.items() if m["source"] == "fantasypros_expert_ros" and not m["stale"])
stale_experts = sorted(l for l, m in META.items() if m["source"] == "fantasypros_expert_ros" and m["stale"])
report = {"provenance": K.provenance(), "lists": META, "fresh_experts": fresh_experts, "stale_experts": stale_experts, "scorings": {}}

for s in SCORINGS:
    pub = load_pub(s)
    curves = {p: sorted([v for (_, pp, v) in pub.values() if pp == p], reverse=True) for p in POS}
    pubpos = {p: {k: v for k, (_, pp, v) in pub.items() if pp == p} for p in POS}
    pubrank = {p: ranks_by_value(list(pubpos[p].items())) for p in POS}
    L = LISTS[s]
    panels = {"consensus": ["consensus", "pianowski", "karabell"],
              "experts": [e for e in fresh_experts if e in L] + ["pianowski", "karabell"]}
    res = {"panel_sizes": {k: len(v) for k, v in panels.items()}, "players": {}, "agreement": {}, "summary": {}}
    for p in POS:
        top = {k: r for k, r in pubrank[p].items() if r <= DEPTH[p]}
        fresh_mean_rank = {k: st.mean([L[e][p][k] for e in fresh_experts if e in L and k in L[e].get(p, {})])
                           for k in top if any(k in L[e].get(p, {}) for e in fresh_experts if e in L)}
        res["agreement"][p] = {
            "consensus_vs_fresh_expert_mean": spearman({k: L["consensus"][p][k] for k in top if k in L["consensus"][p]},
                                                       fresh_mean_rank),
            "consensus_vs_published": spearman(top, {k: L["consensus"][p][k] for k in top if k in L["consensus"][p]}),
            "fresh_expert_mean_vs_published": spearman(top, fresh_mean_rank),
            "each_fresh_expert_vs_published_median": st.median(
                [x for x in (spearman(top, {k: L[e][p][k] for k in top if k in L[e][p]}) for e in fresh_experts if e in L)
                 if x is not None]),
        }
        for k, rp in top.items():
            d = {"pos": p, "published": pubpos[p][k], "published_pos_rank": rp}
            for pn, members in panels.items():
                vals = {m: round(interp(curves[p], L[m][p][k]), 1) for m in members
                        if k in L[m].get(p, {}) and interp(curves[p], L[m][p][k]) is not None}
                v = list(vals.values())
                d[pn] = {"n": len(v), "mean": round(st.mean(v), 1) if v else None,
                         "range": [min(v), max(v)] if v else None,
                         "iqr": round(st.quantiles(v, n=4)[2] - st.quantiles(v, n=4)[0], 1) if len(v) >= 4 else None,
                         "by_list": vals if pn == "consensus" else None}
            res["players"][pub[k][0]] = d
    pl = list(res["players"].values())
    summ = {}
    for pn in panels:
        have = [d for d in pl if d[pn]["mean"] is not None]
        div = [d for d in have if material(d[pn]["mean"] - d["published"], d["published"])]
        summ[pn] = {
            "compared": len(have), "material_vs_published": len(div),
            "median_abs_gap": {p: round(st.median([abs(d[pn]["mean"] - d["published"]) for d in have if d["pos"] == p]), 1) for p in POS},
            "median_spread_pts": {p: round(st.median([d[pn]["range"][1] - d[pn]["range"][0] for d in have if d["pos"] == p and d[pn]["n"] > 1]), 1) for p in POS},
        }
        if pn == "experts":
            summ[pn]["median_iqr_pts"] = {p: round(st.median([d[pn]["iqr"] for d in have if d["pos"] == p and d[pn]["iqr"] is not None]), 1) for p in POS}
    both = [d for d in pl if d["consensus"]["mean"] is not None and d["experts"]["mean"] is not None]
    summ["panels_disagree_materially"] = sorted(
        ((round(d["experts"]["mean"] - d["consensus"]["mean"], 1), n) for n, d in res["players"].items()
         if d in both and material(d["experts"]["mean"] - d["consensus"]["mean"], d["consensus"]["mean"])),
        key=lambda x: -abs(x[0]))
    summ["largest_vs_published_experts"] = sorted(
        ((round(d["experts"]["mean"] - d["published"], 1), n) for n, d in res["players"].items()
         if d["experts"]["mean"] is not None and material(d["experts"]["mean"] - d["published"], d["published"])),
        key=lambda x: -abs(x[0]))[:14]
    res["summary"] = summ
    report["scorings"][s] = res

report["joins"] = K.join_report()
json.dump(report, open(W / "ros_rank_panels_out.json", "w"), indent=1)
print("fresh expert lists:", len(fresh_experts), fresh_experts)
print("stale expert lists:", len(stale_experts), {e: META[e]["vintages"].get("RB") for e in stale_experts})
for s in SCORINGS:
    r = report["scorings"][s]
    print(f"\n===== {s} ===== panel sizes {r['panel_sizes']}")
    for p in POS:
        print(p, r["agreement"][p])
    print("summary", json.dumps({k: v for k, v in r["summary"].items() if k != "largest_vs_published_experts"}))
    print("largest vs published (expert panel)", r["summary"]["largest_vs_published_experts"])
    for n in ["Chase Brown", "Malik Nabers", "Drake Maye", "Jalen Coker", "Josh Jacobs", "Breece Hall"]:
        d = r["players"].get(n)
        if d:
            print(f"  {n}: pub {d['published']} (#{d['published_pos_rank']}) consensus panel {d['consensus']['mean']} "
                  f"{d['consensus']['range']} | expert panel {d['experts']['mean']} n={d['experts']['n']} "
                  f"range {d['experts']['range']} iqr {d['experts']['iqr']}")
