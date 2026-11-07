#!/usr/bin/env python3
"""Evidence for the trade value source audit (JEG-1565, private draft article).

Reads only files in this repo and writes one JSON the article page loads
(app/next/research/trade-value-audit-data.json). Every number on the page comes
from this output; tests/test_research_trade_value_audit.py re-runs it and checks
the page's JSON and the numbers quoted in its text equal the output.

Inputs (week 9, 2026 snapshot):
  data/fixtures/current/comparison-sources-data.json  published chart values
  data/fixtures/current/players.json                   projections, names, positions
  data/history/week-5.json .. week-9.json              one frozen snapshot per week
  pipelines/value_reference.py                         our value model (the yardstick)

Run:  python3 pipelines/research_trade_value_audit.py [--out PATH] [--check]
--check exits 1 when PATH differs from a fresh run (the page data is stale).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from itertools import combinations
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
import value_reference as vr  # noqa: E402
from lib.canonical_players import norm_player_name  # noqa: E402  (the one name rule, JEG-438)

OUT = REPO / "app" / "next" / "research" / "trade-value-audit-data.json"
HISTORY_DIR = REPO / "data" / "history"
SNAPSHOT_DAY = date(2026, 11, 7)  # pins value_reference's week logic so reruns match
WEEKS = (5, 6, 7, 8, 9)
POS = vr.POSITIONS
FLEX = ("RB", "WR", "TE")
CHARTS = ("cbs", "usatoday", "fantasypros", "fantasycalc")
PROJ = ("espn", "cbsros", "razzball")
NAMES = {"cbs": "CBS Sports", "usatoday": "USA Today", "fantasypros": "FantasyPros",
         "fantasycalc": "FantasyCalc", "espn": "ESPN", "cbsros": "CBS rest-of-season projections",
         "razzball": "Razzball"}
SCORING_LABEL = {"standard": "Standard", "half_ppr": "Half PPR", "ppr": "Full PPR"}
HIST_INDEX = vr.HISTORY_SCORING_INDEX
BASE = {"scoring": "half_ppr", "teams": 12, "superflex": 0}
TOP_N = 50          # model-free position mix: the source's own top 50
CURVE_N = 120       # overall curve length drawn on the page
TRADE_POOL = 150    # players offered in the trade-it-yourself box
SCORING_TOP = 36    # players per position compared across scoring formats
WEEKLY_TOP = 24     # players per position followed week to week
OUTLIER_DEPTH = 36  # an outlier must be a top-36 player at his position on that chart or by the others


def r(x, nd=1):
    return None if x is None else round(float(x), nd)


def spearman(a: list, b: list) -> float | None:
    """Spearman rank correlation (average ranks for ties)."""
    n = len(a)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        out = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                out[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return out

    ra, rb = ranks(a), ranks(b)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va and vb else None


def load():
    inp = vr.Inputs.load(today=SNAPSHOT_DAY)
    return inp


def setting(inp, scoring="half_ppr", teams=12, superflex=0):
    return vr.Setting(inp, scoring, teams, superflex)


def pos_shares(diag_src: dict) -> dict:
    w = diag_src["weights"] or {}
    return {p: w.get(f"{p}|starter", 0.0) + w.get(f"{p}|bench", 0.0) for p in POS}


def mean_shares(list_of: list) -> dict:
    return {p: sum(s[p] for s in list_of) / len(list_of) for p in POS}


def pct(d: dict) -> dict:
    return {p: r(100 * d[p], 1) for p in POS}


def l1_points(a: dict, b: dict) -> float:
    """Half the sum of absolute share differences, in percentage points:
    the share of value that would have to move between positions to match."""
    return 50 * sum(abs(a[p] - b[p]) for p in POS)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def source_meta(inp, base_diag) -> dict:
    out = {}
    for k in (*CHARTS, *PROJ):
        sec = inp.section(k) or {}
        hold = sec.get("validationHold") or sec.get("promotionHold")
        d = base_diag["sources"].get(k, {})
        positions = d.get("positions", {})
        out[k] = {
            "name": NAMES[k], "family": vr.FAMILY[k],
            "kind": sec.get("kind"), "fetched_at": sec.get("fetched_at"),
            "content_vintage": sec.get("content_vintage") or sec.get("vintage"),
            "claimed_settings": sec.get("claimed_settings"),
            "held_this_week": bool(hold),
            "hold_reason": (hold or {}).get("reason") if isinstance(hold, dict) else None,
            "hold_level": (hold or {}).get("hold_level") if isinstance(hold, dict) else None,
            "listed": {p: positions.get(p, {}).get("listed") for p in POS},
            "rostered": {p: positions.get(p, {}).get("rostered") for p in POS},
            "filled_in": {p: positions.get(p, {}).get("nEstimated") for p in POS},
        }
    return out


def position_weighting(inp) -> dict:
    cases = {
        "half_ppr/12/1qb": ("half_ppr", 12, 0), "half_ppr/12/sf": ("half_ppr", 12, 1),
        "standard/12/1qb": ("standard", 12, 0), "ppr/12/1qb": ("ppr", 12, 0),
    }
    out = {}
    for cid, (sc, t, sf) in cases.items():
        diag = setting(inp, sc, t, sf).diagnostics()
        shares = {k: pos_shares(diag["sources"][k]) for k in (*CHARTS, *PROJ) if k in diag["sources"]}
        proj_mean = mean_shares([shares[k] for k in PROJ])
        chart_mean = mean_shares([shares[k] for k in CHARTS])
        out[cid] = {
            "sources": {k: pct(v) for k, v in shares.items()},
            "projections_mean": pct(proj_mean),
            "analyst_charts_mean": pct(mean_shares([shares[k] for k in ("cbs", "usatoday", "fantasypros")])),
            "charts_mean": pct(chart_mean),
            "gap_vs_projections": {k: r(l1_points(shares[k], proj_mean), 1) for k in CHARTS},
        }
    return out


def overall_order(values: dict, pos_of: dict) -> list:
    return sorted((i for i in values if pos_of.get(i) in POS), key=lambda i: (-values[i], i))


def top_mix(inp, s) -> dict:
    pos_of = s.pos_of
    out = {}
    for k in CHARTS:
        order = overall_order(s.natives(k), pos_of)[:TOP_N]
        out[k] = {p: sum(1 for i in order if pos_of[i] == p) for p in POS}
    return out


def scoring_awareness(inp) -> dict:
    """Does a source change between Standard and Full PPR? For each position,
    the top SCORING_TOP players by Full PPR value that both lists carry: the
    share whose number changes, and the share whose place in the order changes."""
    std, full = setting(inp, "standard"), setting(inp, "ppr")
    pos_of = std.pos_of
    out = {}
    for k in (*CHARTS, *PROJ):
        a, b = std.natives(k), full.natives(k)
        row = {}
        for p in POS:
            common = [i for i in a if i in b and pos_of.get(i) == p]
            common = sorted(common, key=lambda i: (-b[i], i))[:SCORING_TOP]
            changed = sum(1 for i in common if abs(a[i] - b[i]) > 1e-9)
            order_a = sorted(common, key=lambda i: (-a[i], i))
            order_b = sorted(common, key=lambda i: (-b[i], i))
            moved = sum(1 for x, y in zip(order_a, order_b) if x != y)
            row[p] = {"n": len(common), "changed_pct": r(100 * changed / len(common), 0) if common else None,
                      "order_changed_pct": r(100 * moved / len(common), 0) if common else None,
                      "rank_corr": r(spearman([a[i] for i in common], [b[i] for i in common]), 3)}
        out[k] = row
    return out


def superflex(inp, pw) -> dict:
    base, sf = setting(inp, "half_ppr", 12, 0), setting(inp, "half_ppr", 12, 1)
    pos_of = base.pos_of
    out = {}
    for k in CHARTS:
        one, two = base.natives(k), sf.natives(k)
        cell = inp.cell(k, "half_ppr", 12, "native_superflex")
        sf_qbs = sum(1 for i in (cell or {}).get("values", {}) if pos_of.get(i) == "QB")
        top_q1 = max((v for i, v in one.items() if pos_of[i] == "QB"), default=None)
        top_q2 = max((v for i, v in two.items() if pos_of[i] == "QB"), default=None)
        top_nonqb = max((v for i, v in one.items() if pos_of[i] != "QB"), default=None)
        out[k] = {
            "superflex_qbs_listed": sf_qbs,
            "qb_share_1qb": pw["half_ppr/12/1qb"]["sources"][k]["QB"],
            "qb_share_sf": pw["half_ppr/12/sf"]["sources"][k]["QB"],
            "top_qb_vs_top_player_1qb_pct": r(100 * top_q1 / top_nonqb, 0) if top_q1 and top_nonqb else None,
            "top_qb_vs_top_player_sf_pct": r(100 * top_q2 / top_nonqb, 0) if top_q2 and top_nonqb else None,
        }
    for k in PROJ:
        out[k] = {"qb_share_1qb": pw["half_ppr/12/1qb"]["sources"][k]["QB"],
                  "qb_share_sf": pw["half_ppr/12/sf"]["sources"][k]["QB"]}
    return out


def ddf_values(s) -> dict:
    """Our DDF Value (the model's mean of the four charts' Adjusted values)."""
    idx = s.rows("indexed")
    return {i: v["ddf_value"] for i, v in idx.items() if v.get("ddf_value") is not None}


def curves(inp) -> dict:
    """Each chart's overall value curve, #1 = 100, ranks 1..CURVE_N, per scoring;
    plus curve statistics at half PPR."""
    out = {"curves": {}, "stats": {}, "curve_players": {}}
    for sc in vr.SCORINGS:
        s = setting(inp, sc)
        out["curves"][sc] = {}
        for k in CHARTS:
            nat = s.natives(k)
            order = overall_order(nat, s.pos_of)
            top = nat[order[0]]
            out["curves"][sc][k] = [r(100 * nat[i] / top, 1) for i in order[:CURVE_N]]
            out["curve_players"].setdefault(sc, {})[k] = [[inp.players[i]["name"], s.pos_of[i]] for i in order[:CURVE_N]]
        ddf = ddf_values(s)
        order = overall_order(ddf, s.pos_of)
        out["curves"][sc]["ddf"] = [r(100 * ddf[i] / ddf[order[0]], 1) for i in order[:CURVE_N]]
        out["curve_players"][sc]["ddf"] = [[inp.players[i]["name"], s.pos_of[i]] for i in order[:CURVE_N]]
    s = setting(inp)
    diag = s.diagnostics()
    for k in CHARTS:
        nat = s.natives(k)
        order = overall_order(nat, s.pos_of)
        top = nat[order[0]]
        pos_top = {p: max(v for i, v in nat.items() if s.pos_of[i] == p) for p in POS}
        waiver = {p: diag["sources"][k]["positions"][p]["waiver"] for p in POS}
        at = lambda n: r(100 * nat[order[n - 1]] / top, 0) if len(order) >= n else None  # noqa: E731
        out["stats"][k] = {
            "listed_total": len(order),
            "rank12_pct": at(12), "rank24_pct": at(24), "rank50_pct": at(50), "rank100_pct": at(100),
            "waiver_pct_of_position_top": {p: r(100 * waiver[p] / pos_top[p], 1) for p in POS},
            "waiver_pct_of_overall_top": {p: r(100 * waiver[p] / top, 1) for p in POS},
        }
    for k in CHARTS:
        nat = s.natives(k)
        top = max(nat.values())
        out["stats"][k]["position_top_pct"] = {
            p: r(100 * max(v for i, v in nat.items() if s.pos_of[i] == p) / top, 0) for p in POS}
    ddf = ddf_values(s)
    order = overall_order(ddf, s.pos_of)
    out["stats"]["ddf"] = {"position_top_pct": {
        p: r(100 * max(v for i, v in ddf.items() if s.pos_of[i] == p) / ddf[order[0]], 0) for p in POS},"listed_total": len(order),
                           **{f"rank{n}_pct": r(100 * ddf[order[n - 1]] / ddf[order[0]], 0) for n in (12, 24, 50, 100)}}
    return out


def consolidation(inp) -> dict:
    """2-for-1 test at half PPR: of all pairs of players ranked 25-60 on a
    chart, the share whose summed chart value is strictly greater than each top-12 player's, raw
    and after each piece's own waiver-line value is subtracted (the receiving
    team cuts a waiver-level player to make room)."""
    s = setting(inp)
    diag = s.diagnostics()
    out = {}
    for k in CHARTS:
        nat = s.natives(k)
        order = overall_order(nat, s.pos_of)
        waiver = {p: diag["sources"][k]["positions"][p]["waiver"] for p in POS}
        vaw = {i: max(0.0, nat[i] - waiver[s.pos_of[i]]) for i in order}
        stars, mids = order[:12], order[24:60]
        pairs = list(combinations(mids, 2))
        raw_hits = vaw_hits = 0
        for st in stars:
            raw_hits += sum(1 for a, b in pairs if nat[a] + nat[b] > nat[st])
            vaw_hits += sum(1 for a, b in pairs if vaw[a] + vaw[b] > vaw[st])
        total = len(stars) * len(pairs)
        out[k] = {"pairs_tested": total, "raw_beats_star_pct": r(100 * raw_hits / total, 0),
                  "after_waiver_beats_star_pct": r(100 * vaw_hits / total, 0)}
    ddf = ddf_values(s)  # already value above waivers: nothing to subtract
    order = overall_order(ddf, s.pos_of)
    stars, pairs = order[:12], list(combinations(order[24:60], 2))
    hits = sum(1 for st in stars for a, b in pairs if ddf[a] + ddf[b] > ddf[st])
    out["ddf"] = {"pairs_tested": len(stars) * len(pairs),
                  "after_waiver_beats_star_pct": r(100 * hits / (len(stars) * len(pairs)), 0)}
    return out


def agreement(inp) -> dict:
    s = setting(inp)
    pos_of = s.pos_of
    nat = {k: s.natives(k) for k in CHARTS}
    common = [i for i in nat["cbs"] if all(i in nat[k] for k in CHARTS)]
    matrix = {}
    for a, b in combinations(CHARTS, 2):
        matrix[f"{a}|{b}"] = r(spearman([nat[a][i] for i in common], [nat[b][i] for i in common]), 3)
    by_pos = {}
    for p in POS:
        cp = [i for i in common if pos_of[i] == p]
        by_pos[p] = {f"{a}|{b}": r(spearman([nat[a][i] for i in cp], [nat[b][i] for i in cp]), 3)
                     for a, b in combinations(CHARTS, 2)}
        by_pos[p]["n"] = len(cp)
    return {"n_common": len(common), "overall": matrix, "by_position": by_pos}


def player_rows(inp) -> tuple[list, dict]:
    """Top TRADE_POOL players by DDF Value at half PPR / 12 teams, with each
    chart's published number and his rank at his position on each chart."""
    s = setting(inp)
    diag = s.diagnostics()
    pos_of = s.pos_of
    nat = {k: s.natives(k) for k in CHARTS}
    pos_rank = {}
    for k in CHARTS:
        pos_rank[k] = {}
        for p in POS:
            order = sorted((i for i in nat[k] if pos_of.get(i) == p), key=lambda i: (-nat[k][i], i))
            pos_rank[k].update({i: n + 1 for n, i in enumerate(order)})
    waiver = {k: {p: diag["sources"][k]["positions"][p]["waiver"] for p in POS} for k in CHARTS}
    ddf = ddf_values(s)
    ranked = sorted(ddf, key=lambda i: (-ddf[i], i))[:TRADE_POOL]
    rows = []
    for i in ranked:
        rows.append({"key": i, "name": inp.players[i]["name"], "pos": pos_of[i], "ddf": r(ddf[i], 1),
                     "published": {k: nat[k].get(i) for k in CHARTS},
                     "pos_rank": {k: pos_rank[k].get(i) for k in CHARTS}})
    return rows, {k: {p: r(waiver[k][p], 2) for p in POS} for k in CHARTS}


def outliers(rows: list) -> list:
    """Largest gap between one chart's rank for a player at his position and
    the median rank the other three charts give him (all four must list him,
    and either rank must be inside the top OUTLIER_DEPTH).
    Ranks, not values, so a flat or steep curve cannot fake a disagreement."""
    out = []
    for row in rows:
        rk = row["pos_rank"]
        if any(rk[k] is None for k in CHARTS):
            continue
        for k in CHARTS:
            med = sorted(rk[o] for o in CHARTS if o != k)[1]
            if min(rk[k], med) > OUTLIER_DEPTH:
                continue
            out.append({"name": row["name"], "pos": row["pos"], "source": k, "rank": rk[k],
                        "others_median_rank": med, "gap": rk[k] - med})
    out.sort(key=lambda x: (-abs(x["gap"]), x["name"], x["source"]))
    return out


def fantasycalc_scoring_factors(inp) -> dict:
    """FantasyCalc Full PPR / Standard, per position, over the top SCORING_TOP:
    median ratio and the spread (max - min) of the ratio."""
    std, full = setting(inp, "standard"), setting(inp, "ppr")
    a, b = std.natives("fantasycalc"), full.natives("fantasycalc")
    out = {}
    for p in POS:
        common = sorted((i for i in a if i in b and std.pos_of.get(i) == p and a[i] > 0),
                        key=lambda i: (-b[i], i))[:SCORING_TOP]
        ratios = sorted(b[i] / a[i] for i in common)
        out[p] = {"n": len(ratios), "median_ratio": r(ratios[len(ratios) // 2], 3),
                  "spread": r(ratios[-1] - ratios[0], 3)}
    return out


def weekly(inp) -> dict:
    """Week-over-week change of each source's own numbers (half PPR), weeks 5-9.
    rank_move: mean absolute change in position rank of last week's top
    WEEKLY_TOP players at each position that are listed both weeks (scale-free).
    unchanged_pct: share of those players whose number is exactly the same."""
    docs = {w: json.loads((HISTORY_DIR / f"week-{w}.json").read_text(encoding="utf-8")) for w in WEEKS}
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    out = {}
    for k in (*CHARTS, *PROJ):
        dates, moves, unchanged = [], [], []
        prev = None
        for w in WEEKS:
            sec = docs[w]["sources"][k]
            dates.append(str(sec["_sort"][0])[:10])
            if vr.FAMILY[k] == "chart":
                cur = {int(x): v for x, v in sec["natives"]["half_ppr"].items()}
            else:
                cur = {int(x): v[HIST_INDEX["half_ppr"]] for x, v in sec["ppg"].items()
                       if v and v[HIST_INDEX["half_ppr"]]}
            cur = {i: v for i, v in cur.items() if pos_of.get(i) in POS}
            if prev is not None:
                deltas, same = [], 0
                for p in POS:
                    both = [i for i in prev if i in cur and pos_of[i] == p]
                    rank_prev = {i: n for n, i in enumerate(sorted(both, key=lambda i: (-prev[i], i)))}
                    rank_cur = {i: n for n, i in enumerate(sorted(both, key=lambda i: (-cur[i], i)))}
                    top = sorted(both, key=lambda i: (-prev[i], i))[:WEEKLY_TOP]
                    deltas += [abs(rank_cur[i] - rank_prev[i]) for i in top]
                    same += sum(1 for i in top if cur[i] == prev[i])
                moves.append(r(sum(deltas) / len(deltas), 2) if deltas else None)
                unchanged.append(r(100 * same / len(deltas), 0) if deltas else None)
            prev = cur
        out[k] = {"weeks": list(WEEKS), "snapshot_dates": dates,
                  "rank_move": moves, "unchanged_pct": unchanged}
    return out


# ---------------------------------------------------------------------------
# Scorecard (rules printed on the page)
# ---------------------------------------------------------------------------

RULES = {
    "balance": "Position balance: share of value that would have to move between positions to match the projections (ESPN, CBS rest-of-season, Razzball run through our model), Half PPR, 12 teams. Strong up to 5 points, OK up to 10, Weak above 10.",
    "scoring": "Scoring formats: compare Standard with Full PPR for the top 36 at RB, WR and TE. Strong when at least 20% of those players change places on average; OK when the numbers change but fewer change places; Weak when the numbers do not change. For ESPN the formats are our scoring of its projected stats, for CBS rest-of-season we add points per catch to its Standard total; Razzball publishes its own columns.",
    "superflex": "Superflex: Strong with superflex values for 24 or more QBs (two per team); OK with fewer; Weak with none.",
    "league_size": "League size: Strong when the source offers its own numbers by team count; Weak with one table for every league size.",
    "depth": "Depth: the thinnest position's listed players as a share of the players a 12-team league rosters there. Strong at 100% or more, OK at 70% or more, Weak below.",
    "freshness": "Freshness: Strong when each of the four week-to-week changes from week 5 to 9 is a new publication and moves last week's top 24 per position by at least a quarter of a rank on average; OK when one week did not; Weak otherwise.",
    "consolidation": "2-for-1 sense: the share of mid-tier pairs (ranks 25-60) that the raw chart says beat a top-12 player, minus the share once each player's waiver-level value is subtracted. Strong up to 10 points of difference, OK up to 25, Weak above 25.",
}
LEVEL = {3: "Strong", 2: "OK", 1: "Weak", None: "Not measured"}


def grade(x, strong, ok, higher_is_better=False):
    if x is None:
        return None
    if higher_is_better:
        return 3 if x >= strong else 2 if x >= ok else 1
    return 3 if x <= strong else 2 if x <= ok else 1


def scoring_level(sc_k):
    moved = [sc_k[p]["order_changed_pct"] or 0 for p in FLEX]
    changed = [sc_k[p]["changed_pct"] or 0 for p in FLEX]
    if sum(moved) / len(moved) >= 20:
        return 3
    return 2 if sum(changed) / len(changed) >= 50 else 1


def fresh_level(wk_k):
    moves = wk_k["rank_move"]
    weeks_ok = sum(1 for m in moves if m is not None and m >= 0.25)
    new_dates = len(set(wk_k["snapshot_dates"])) == len(WEEKS)
    if weeks_ok == len(moves) and new_dates:
        return 3, weeks_ok
    return (2 if weeks_ok >= len(moves) - 1 else 1), weeks_ok


def scorecard(meta, pw, sc, sfx, wk, cons) -> dict:
    out = {}
    league_size_offered = {"fantasycalc"}  # its public values API takes numTeams (pipelines/pull_fantasycalc_12team.py)
    for k in CHARTS:
        gap = pw["half_ppr/12/1qb"]["gap_vs_projections"][k]
        n_sf = sfx[k]["superflex_qbs_listed"]
        depth = min(meta[k]["listed"][p] / meta[k]["rostered"][p] for p in POS)
        fl, fw = fresh_level(wk[k])
        cgap = cons[k]["raw_beats_star_pct"] - cons[k]["after_waiver_beats_star_pct"]
        out[k] = {
            "balance": {"level": grade(gap, 5, 10), "value": gap},
            "scoring": {"level": scoring_level(sc[k])},
            "superflex": {"level": 3 if n_sf >= 24 else 2 if n_sf > 0 else 1, "value": n_sf},
            "league_size": {"level": 3 if k in league_size_offered else 1},
            "depth": {"level": grade(100 * depth, 100, 70, True), "value": r(100 * depth, 0)},
            "freshness": {"level": fl, "value": fw},
            "consolidation": {"level": grade(cgap, 10, 25), "value": r(cgap, 0)},
        }
    for k in PROJ:
        fl, fw = fresh_level(wk[k])
        out[k] = {
            "balance": {"level": None}, "superflex": {"level": None}, "league_size": {"level": None},
            "consolidation": {"level": None}, "depth": {"level": None},
            "scoring": {"level": scoring_level(sc[k])},
            "freshness": {"level": fl, "value": fw},
        }
    for k in out:
        for dim in out[k].values():
            dim["label"] = LEVEL[dim["level"]]
    return out



# ---------------------------------------------------------------------------
# DynastyProcess (open data, GPL-3.0): data/research/jeg1565/dynastyprocess
# ---------------------------------------------------------------------------

DP = "dynastyprocess"
DP_DIR = REPO / "data" / "research" / "jeg1565" / "dynastyprocess"
DP_DATES = ("2026-10-09", "2026-10-16", "2026-10-23", "2026-10-30", "2026-11-06")
DP_CURRENT = DP_DATES[-1]
AGE_BANDS = ((0, 25, "under 25"), (25, 28, "25 to 27"), (28, 30, "28 to 29"), (30, 99, "30 and over"))


FC_DIR = REPO / "data" / "research" / "jeg1565" / "fantasycalc"
FC_RAW_WEEK4 = REPO / "data" / "raw" / "sources" / "fantasycalc" / "week-4" / "snapshot.json"


def _reorder(a: dict, b: dict, pos_of: dict) -> dict:
    """Top SCORING_TOP by Full PPR value at RB, WR and TE: how many change places
    between Standard (a) and Full PPR (b), and the spread of the Full/Standard ratio."""
    out = {}
    for p in FLEX:
        top = sorted((k for k in a if k in b and pos_of.get(k) == p and a[k] > 0), key=lambda k: (-b[k], k))[:SCORING_TOP]
        ratios = [b[k] / a[k] for k in top]
        oa, ob = sorted(top, key=lambda k: (-a[k], k)), sorted(top, key=lambda k: (-b[k], k))
        out[p] = {"n": len(top), "reordered": sum(1 for x, y in zip(oa, ob) if x != y),
                  "ratio_spread": r(max(ratios) - min(ratios), 3) if ratios else None}
    return out


def scoring_provenance(inp) -> dict:
    """Is a chart's Standard-vs-Full difference in the publisher's own output?
    FantasyCalc: one request per format (ppr=0 / ppr=1); every capture we hold.
    Charts: share of players whose Standard and Full PPR numbers are identical,
    per weekly snapshot (the as-published natives)."""
    pos_of = {k: p["pos"] for k, p in inp.players.items()}
    fc = []
    caps = json.loads((FC_DIR / "captures.json").read_text(encoding="utf-8"))
    for label in ("week 4 cache", "live pull"):
        side = {c["scoring"]: c for c in caps if c["label"] == label}
        a = {x["name"]: x["value"] for x in side["standard"]["rows"]}
        b = {x["name"]: x["value"] for x in side["full"]["rows"]}
        names = {x["name"]: x["pos"] for x in side["standard"]["rows"]}
        fc.append({"capture": label, "fetched_at": side["full"]["fetched_at"],
                   "urls": [side["standard"]["source_url"], side["full"]["source_url"]], **_reorder(a, b, names)})
    raw = json.loads(FC_RAW_WEEK4.read_text(encoding="utf-8"))
    a = {x["player_name"]: x["native_value"] for x in raw["rows"] if x["scoring"] == "standard"}
    b = {x["player_name"]: x["native_value"] for x in raw["rows"] if x["scoring"] == "ppr"}
    names = {x["player_name"]: x["pos"] for x in raw["rows"]}
    fc.append({"capture": "week 4 raw snapshot", "fetched_at": raw["fetched_at"], **_reorder(a, b, names)})
    identical = {}
    for w in WEEKS:
        doc = json.loads((HISTORY_DIR / f"week-{w}.json").read_text(encoding="utf-8"))
        for k in CHARTS:
            n = doc["sources"][k]["natives"]
            a = {int(x): v for x, v in n["standard"].items()}
            b = {int(x): v for x, v in n["ppr"].items()}
            common = [x for x in a if x in b]
            identical.setdefault(k, []).append(r(100 * sum(1 for x in common if a[x] == b[x]) / len(common), 0))
            if k == "fantasycalc":
                fc.append({"capture": f"week {w} snapshot", "fetched_at": str(doc["sources"][k]["_sort"][0]),
                           **_reorder(a, b, pos_of)})
    order = {"week 4 cache": 0, "week 4 raw snapshot": 1, "live pull": 99}
    fc.sort(key=lambda x: (order.get(x["capture"], 50), x["capture"]))
    reordered = [sum(x[p]["reordered"] for p in FLEX) for x in fc]
    return {"fantasycalc_captures": fc, "identical_std_vs_ppr_pct_by_week": identical,
            "fantasycalc_captures_with_reorder": sum(1 for v in reordered if v > 0),
            "fantasycalc_captures_total": len(fc)}


def dp_snapshot(inp, day: str) -> dict:
    """{player_key: {"v1", "v2", "age"}} from the stored file, matched by
    normalized name and position; names that match no player, or more than
    one, are counted in "unmatched"."""
    import csv
    by = {}
    for k, p in inp.players.items():
        by.setdefault((norm_player_name(p["name"]), p["pos"]), []).append(k)
    out, unmatched, unmatched_max = {}, 0, 0.0
    with open(DP_DIR / f"values-players-{day}.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["pos"] not in POS:
                continue
            keys = by.get((norm_player_name(row["player"]), row["pos"]))
            if not keys or len(keys) > 1:
                unmatched += 1
                unmatched_max = max(unmatched_max, float(row["value_1qb"]))
                continue
            out[keys[0]] = {"v1": float(row["value_1qb"]), "v2": float(row["value_2qb"]),
                            "age": float(row["age"]) if row["age"] not in ("", "NA") else None}
    top = max((v["v1"] for v in out.values()), default=1.0)
    return {"players": out, "unmatched": unmatched, "unmatched_max_pct": round(100 * unmatched_max / top, 1)}


def dp_run(inp, snap: dict, scoring="half_ppr", superflex=0, teams=12):
    """Our model run with DynastyProcess added as one more chart, read for its
    own diagnostics only (the other sources' numbers come from runs without it).
    DynastyProcess publishes one value set for every scoring format; in
    superflex its 2QB column prices every player it lists."""
    s = setting(inp, scoring, teams, superflex)
    st = s.state()
    field = "v2" if superflex else "v1"
    nat = {k: v[field] for k, v in snap["players"].items()}
    srcs = s._sources(st["current"])
    srcs[DP] = vr.SourceInput(DP, "chart", dict(nat))
    res = vr.run_pipeline(s.league, srcs, s.pos_of, list(st["included"]) + [DP], s.selection,
                          lineup=s.lineup, hidden=st.get("hidden"), promotion_model=s.promotion_model,
                          flex_bench_seats=s.flex_bench_seats, basis=s.basis)
    return s, nat, res["sources"][DP]


def dynastyprocess(inp, data: dict) -> dict:
    snap = dp_snapshot(inp, DP_CURRENT)
    pw = data["position_weighting"]
    out = {"matched": len(snap["players"]), "unmatched": snap["unmatched"],
           "unmatched_max_pct": snap["unmatched_max_pct"], "snapshot": DP_CURRENT}
    shares = {}
    for cid, (sc, sf) in {"half_ppr/12/1qb": ("half_ppr", 0), "half_ppr/12/sf": ("half_ppr", 1),
                          "standard/12/1qb": ("standard", 0), "ppr/12/1qb": ("ppr", 0)}.items():
        _, _, det = dp_run(inp, snap, sc, sf)
        w = det["weights"]
        shares[cid] = pct({p: w[f"{p}|starter"] + w[f"{p}|bench"] for p in POS})
        proj = {p: pw[cid]["projections_mean"][p] / 100 for p in POS}
        out.setdefault("gap_vs_projections", {})[cid] = r(l1_points({p: shares[cid][p] / 100 for p in POS}, proj), 1)
    out["shares"] = shares
    s, nat, det = dp_run(inp, snap)
    pos_of = s.pos_of
    order = overall_order(nat, pos_of)
    top = nat[order[0]]
    waiver = {p: det["positions"][p]["waiver_value"] for p in POS}
    out["listed"] = {p: det["positions"][p]["listed"] for p in POS}
    out["rostered"] = {p: det["positions"][p]["rostered"] for p in POS}
    out["filled_in"] = {p: len(det["positions"][p]["imputation_ratios"] or {}) for p in POS}
    out["waiver_line"] = {p: r(waiver[p], 2) for p in POS}
    out["top50_mix"] = {p: sum(1 for i in order[:TOP_N] if pos_of[i] == p) for p in POS}
    out["curve"] = [r(100 * nat[i] / top, 1) for i in order[:CURVE_N]]
    out["curve_players"] = [[inp.players[i]["name"], pos_of[i]] for i in order[:CURVE_N]]
    out["curve_stats"] = {
        "listed_total": len(order),
        **{f"rank{n}_pct": r(100 * nat[order[n - 1]] / top, 0) for n in (12, 24, 50, 100)},
        "position_top_pct": {p: r(100 * max(v for i, v in nat.items() if pos_of[i] == p) / top, 0) for p in POS},
    }
    # 2-for-1, same rule as the charts.
    vaw = {i: max(0.0, nat[i] - waiver[pos_of[i]]) for i in order}
    stars, pairs = order[:12], list(combinations(order[24:60], 2))
    tot = len(stars) * len(pairs)
    raw = sum(1 for st in stars for a, b in pairs if nat[a] + nat[b] > nat[st])
    aft = sum(1 for st in stars for a, b in pairs if vaw[a] + vaw[b] > vaw[st])
    out["consolidation"] = {"pairs_tested": tot, "raw_beats_star_pct": r(100 * raw / tot, 0),
                            "after_waiver_beats_star_pct": r(100 * aft / tot, 0)}
    # Superflex: the 2QB column.
    sf_qbs = sum(1 for k, v in snap["players"].items() if pos_of.get(k) == "QB" and v["v2"] > 0)
    out["superflex"] = {"superflex_qbs_listed": sf_qbs, "qb_share_1qb": shares["half_ppr/12/1qb"]["QB"],
                        "qb_share_sf": shares["half_ppr/12/sf"]["QB"]}
    # Agreement with the four redraft charts (players both list), Half PPR.
    base = setting(inp)
    out["rank_corr_with"] = {}
    for k in CHARTS:
        other = base.natives(k)
        common = [i for i in nat if i in other]
        out["rank_corr_with"][k] = r(spearman([nat[i] for i in common], [other[i] for i in common]), 3)
    # Like for like: the players all four redraft charts list (the set behind agreement()).
    four = {k: base.natives(k) for k in CHARTS}
    common4 = [i for i in four["cbs"] if all(i in four[k] for k in CHARTS) and i in nat]
    out["rank_corr_common"] = {"n": len(common4), **{
        k: r(spearman([nat[i] for i in common4], [four[k][i] for i in common4]), 3) for k in CHARTS}}
    out["rank_corr_common_min"] = min(out["rank_corr_common"][k] for k in CHARTS)
    out["rank_corr_common_max"] = max(out["rank_corr_common"][k] for k in CHARTS)
    # Age: position rank on DynastyProcess against position rank by our (redraft) DDF Value.
    ddf = ddf_values(base)
    pool = sorted(ddf, key=lambda i: (-ddf[i], i))[:TRADE_POOL]
    pool = [i for i in pool if i in nat and snap["players"][i]["age"] is not None]
    def prank(values, keys):
        rk = {}
        for p in POS:
            ks = sorted((i for i in keys if pos_of[i] == p), key=lambda i: (-values[i], i))
            rk.update({i: n + 1 for n, i in enumerate(ks)})
        return rk
    rd, rp = prank(ddf, pool), prank(nat, pool)
    bands = []
    for lo, hi, label in AGE_BANDS:
        ks = [i for i in pool if lo <= snap["players"][i]["age"] < hi]
        moves = [rd[i] - rp[i] for i in ks]
        bands.append({"band": label, "n": len(ks), "mean_rank_gain": r(sum(moves) / len(moves), 1) if moves else None})
    out["age_bands"] = bands
    out["age_pool"] = len(pool)
    # Week to week, same rule as the other sources.
    snaps = [dp_snapshot(inp, d)["players"] for d in DP_DATES]
    moves, same = [], []
    for prev, cur in zip(snaps, snaps[1:]):
        deltas, n_same = [], 0
        for p in POS:
            both = [i for i in prev if i in cur and pos_of.get(i) == p]
            rpv = {i: n for n, i in enumerate(sorted(both, key=lambda i: (-prev[i]["v1"], i)))}
            rcu = {i: n for n, i in enumerate(sorted(both, key=lambda i: (-cur[i]["v1"], i)))}
            topk = sorted(both, key=lambda i: (-prev[i]["v1"], i))[:WEEKLY_TOP]
            deltas += [abs(rcu[i] - rpv[i]) for i in topk]
            n_same += sum(1 for i in topk if cur[i]["v1"] == prev[i]["v1"])
        moves.append(r(sum(deltas) / len(deltas), 2))
        same.append(r(100 * n_same / len(deltas), 0))
    out["weekly"] = {"snapshot_dates": list(DP_DATES), "rank_move": moves, "unchanged_pct": same}
    # Scoring: one value set for every format (the file has no scoring columns).
    out["scoring_note"] = "one value set for every scoring format"
    # Trade box rows.
    for row in data["players"]:
        row["published"][DP] = nat.get(row["key"])
    dp_rank = prank(nat, list(nat))
    for row in data["players"]:
        row["pos_rank"][DP] = dp_rank.get(row["key"])
    data["waiver_line"][DP] = out["waiver_line"]
    # Scorecard (balance not graded: dynasty values price future seasons, our yardstick is this season).
    depth = min(out["listed"][p] / out["rostered"][p] for p in POS)
    fresh_weeks = sum(1 for m in moves if m >= 0.25)
    cgap = out["consolidation"]["raw_beats_star_pct"] - out["consolidation"]["after_waiver_beats_star_pct"]
    card = {
        "balance": {"level": None},
        "scoring": {"level": 1},
        "superflex": {"level": 3 if sf_qbs >= 24 else 2 if sf_qbs else 1, "value": sf_qbs},
        "league_size": {"level": 1},
        "depth": {"level": grade(100 * depth, 100, 70, True), "value": r(100 * depth, 0)},
        "freshness": {"level": 3 if fresh_weeks == len(moves) else 2 if fresh_weeks >= len(moves) - 1 else 1,
                      "value": fresh_weeks},
        "consolidation": {"level": grade(cgap, 10, 25), "value": r(cgap, 0)},
    }
    for dim in card.values():
        dim["label"] = LEVEL[dim["level"]]
    data["scorecard"][DP] = card
    return out


DEPTH_TEAMS = (10, 12, 14)
DEPTH_CURVE_MAX = 130   # position ranks drawn in the depth chart


def depth_class(listed: int, rostered: int) -> str:
    """Where a list ends against the waiver line (the first player past the
    league's rostered count): within max(2, 10% of rostered) is near."""
    tol = max(2, round(0.1 * rostered))
    if listed < rostered - tol:
        return "short"
    if listed > rostered + tol:
        return "past"
    return "near"


def depth_vs_waiver(inp, data: dict) -> dict:
    """Each source's list against the waiver line, per position, at 10/12/14
    teams (Half PPR, our default lineup). The waiver line at a position is the
    value of the first player past the number the league rosters there (VP-2)."""
    snap = dp_snapshot(inp, DP_CURRENT)
    out = {"teams": list(DEPTH_TEAMS), "rostered": {}, "sources": {}, "ddf": {}}
    keys = (*CHARTS, DP)
    for t in DEPTH_TEAMS:
        s = setting(inp, "half_ppr", t)
        diag = s.diagnostics()
        pos_of = s.pos_of
        out["rostered"][t] = {p: diag["sources"]["cbs"]["positions"][p]["rostered"] for p in POS}
        _, dp_nat, dp_det = dp_run(inp, snap, "half_ppr", 0, t)
        for k in keys:
            nat = dp_nat if k == DP else s.natives(k)
            positions = dp_det["positions"] if k == DP else None
            row = out["sources"].setdefault(k, {}).setdefault(t, {})
            total = sum(nat.values())
            past_value = 0.0
            for p in POS:
                order = sorted((i for i in nat if pos_of.get(i) == p), key=lambda i: (-nat[i], i))
                ros = out["rostered"][t][p]
                waiver = positions[p]["waiver_value"] if k == DP else diag["sources"][k]["positions"][p]["waiver"]
                top = nat[order[0]]
                last = order[-1]
                beyond = order[ros:]
                past_value += sum(nat[i] for i in beyond)
                row[p] = {"listed": len(order), "rostered": ros, "gap": len(order) - ros,
                          "unpriced": max(0, ros - len(order)), "beyond": max(0, len(order) - ros),
                          "class": depth_class(len(order), ros),
                          "last_name": inp.players[last]["name"], "last_value": nat[last],
                          "last_pct_of_top": r(100 * nat[last] / top, 1),
                          "waiver_pct_of_top": r(100 * waiver / top, 1)}
                if t == 12:
                    row[p]["curve"] = [r(100 * nat[i] / top, 1) for i in order[:DEPTH_CURVE_MAX]]
            row["value_past_line_pct"] = r(100 * past_value / total, 1)
        # Our model against the same line. "Valued" = DDF Value above a token 0.05 (the page states the cutoff).
        ddf = ddf_values(s)
        drow = out["ddf"].setdefault(t, {})
        for p in POS:
            order = sorted((i for i in ddf if pos_of.get(i) == p), key=lambda i: (-ddf[i], i))
            ros = out["rostered"][t][p]
            drow[p] = {"valued": sum(1 for i in order if ddf[i] > 0.05), "rostered": ros,
                       "past_line_valued": sum(1 for i in order[ros:] if ddf[i] > 0.05)}
        tot = sum(v for v in ddf.values() if v > 0)
        past = 0.0
        for p in POS:
            order = sorted((i for i in ddf if pos_of.get(i) == p), key=lambda i: (-ddf[i], i))
            past += sum(max(0.0, ddf[i]) for i in order[out["rostered"][t][p]:])
        drow["value_past_line_pct"] = r(100 * past / tot, 1)
    out["filled_in_12"] = {k: sum(data["sources"][k]["filled_in"].values()) for k in CHARTS}
    return out


def headline(d: dict) -> dict:
    """The numbers the article quotes in its text, gathered in one place."""
    sc, pw, sfx, cons, cs = d["scoring"], d["position_weighting"], d["superflex"], d["consolidation"], d["curve_stats"]
    reorder = {k: r(sum(sc[k][p]["order_changed_pct"] for p in FLEX) / 3, 0) for k in sc}
    sf_chart_qb = [sfx[k]["qb_share_sf"] for k in CHARTS]
    base = pw["half_ppr/12/1qb"]
    wr_tilt = {k: r(base["sources"][k]["WR"] - base["projections_mean"]["WR"], 1) for k in CHARTS}
    return {
        "reorder_avg_pct": reorder,
        "fantasypros_numbers_changed_pct": max(sc["fantasypros"][p]["changed_pct"] for p in POS),
        "fantasycalc_top_flex_reordered": sum(round(sc["fantasycalc"][p]["order_changed_pct"] * sc["fantasycalc"][p]["n"] / 100)
                                              for p in FLEX),
        "fantasycalc_top_flex_compared": sum(sc["fantasycalc"][p]["n"] for p in FLEX),
        "superflex_chart_qb_min": min(sf_chart_qb), "superflex_chart_qb_max": max(sf_chart_qb),
        "superflex_projection_qb": pw["half_ppr/12/sf"]["projections_mean"]["QB"],
        "oneqb_projection_wr": base["projections_mean"]["WR"], "oneqb_projection_rb": base["projections_mean"]["RB"],
        "wr_tilt_vs_projections": wr_tilt,
        "pairs_raw": {k: cons[k]["raw_beats_star_pct"] for k in CHARTS},
        "pairs_after_waiver": {k: cons[k]["after_waiver_beats_star_pct"] for k in (*CHARTS, "ddf")},
        "top_te_pct": {k: cs[k]["position_top_pct"]["TE"] for k in (*CHARTS, "ddf")},
        "rank24_pct": {k: cs[k]["rank24_pct"] for k in (*CHARTS, "ddf")},
        "agreement_min": min(d["agreement"]["overall"].values()),
        "agreement_max": max(d["agreement"]["overall"].values()),
        "held_sources": sorted(k for k, m in d["sources"].items() if m["held_this_week"]),
        "held_count": sum(1 for m in d["sources"].values() if m["held_this_week"]),
        "source_count": len(d["sources"]),
        "superflex_qbs_min": min(sfx[k]["superflex_qbs_listed"] for k in CHARTS),
        "superflex_qbs_max": max(sfx[k]["superflex_qbs_listed"] for k in CHARTS),
        "wr_tilt_min_of_three": min(wr_tilt[k] for k in ("cbs", "fantasycalc", "usatoday")),
        "wr_tilt_max_of_three": max(wr_tilt[k] for k in ("cbs", "fantasycalc", "usatoday")),
        "filled_in_total": {k: sum(d["sources"][k]["filled_in"].values()) for k in CHARTS},
    }


def build() -> dict:
    inp = load()
    base = setting(inp)
    base_diag = base.diagnostics()
    meta = source_meta(inp, base_diag)
    pw = position_weighting(inp)
    sc = scoring_awareness(inp)
    sfx = superflex(inp, pw)
    cv = curves(inp)
    cons = consolidation(inp)
    rows, waiver = player_rows(inp)
    outl = outliers(rows)
    wk = weekly(inp)
    data = {
        "generated_by": "pipelines/research_trade_value_audit.py",
        "ticket": "JEG-1565",
        "fixture_built_at": inp.fixture.get("built_at"),
        "content_week": vr.freshness(inp)["current_week"],
        "base_setting": {**BASE, "roster": vr.roster(0)},
        "pie": base_diag["pie"],
        "ddf_value_inputs": [k for k in base.state()["included"]
                             if vr.FAMILY[k] == "chart" and k not in (base.state().get("hidden") or set())],
        "sources": meta,
        "position_weighting": pw,
        "top50_mix": top_mix(inp, base),
        "scoring": sc,
        "superflex": sfx,
        "curves": cv["curves"],
        "curve_players": cv["curve_players"],
        "curve_stats": cv["stats"],
        "consolidation": cons,
        "agreement": agreement(inp),
        "players": rows,
        "waiver_line": waiver,
        "outliers": outl[:24],
        "fantasycalc_scoring_factors": fantasycalc_scoring_factors(inp),
        "weekly": wk,
        "scorecard": scorecard(meta, pw, sc, sfx, wk, cons),
        "rules": RULES,
    }
    lineup = json.loads((REPO / "config" / "lineup_parameters.json").read_text(encoding="utf-8"))
    data["model_missed_game_rate_pct"] = {p: r(100 * lineup["positions"][p]["m"]["all"], 1) for p in POS}
    # DynastyProcess publishes Value = 10500 * exp(-0.0235 * ECR) (dynastyprocess.com/values, read 2026-11-07).
    dp = lambda rank: 10500 * math.exp(-0.0235 * rank)  # noqa: E731
    data["dynastyprocess_formula"] = {"scale": 10500, "rate": 0.0235,
                                      **{f"rank{n}_pct": r(100 * dp(n) / dp(1), 0) for n in (12, 24, 50, 100)}}
    data["dynastyprocess"] = dynastyprocess(inp, data)
    data["scoring_provenance"] = scoring_provenance(inp)
    data["depth_vs_waiver"] = depth_vs_waiver(inp, data)
    data["headline"] = headline(data)
    return data


def dump(data: dict) -> str:
    return json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    text = dump(build())
    if args.check:
        same = args.out.exists() and args.out.read_text(encoding="utf-8") == text
        print("up to date" if same else f"stale: {args.out}")
        return 0 if same else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
