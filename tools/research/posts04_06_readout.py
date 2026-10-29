#!/usr/bin/env python3
"""Research posts 4, 5 and 6 (JEG-545): the measured examples behind
"How we rescale trade charts", "Missing is not zero, and the one-source rule"
and "Trade confidence".

One command, reproducible, standard library only:

  python3 tools/research/posts04_06_readout.py     # writes docs/research/data/posts04_06/

What it does
  Runs the Python reference engine (pipelines/value_reference.py, which
  value_check holds equal to the browser engine) on the current fixture
  (data/fixtures/current) with the build's own holds and divergence
  exclusions, and reads, for each rule the posts describe, how often it fires
  and one real example:

  Post 4  each chart's one Indexed factor (VP-6.4) at every scoring (standard,
          half PPR, PPR) and 8/10/12/14 teams; that the factor keeps every
          pairwise order of the chart's listed players; and, as a
          counterfactual, how many pairs a per-position factor would invert on
          the same data.
  Post 5  how each chart's row value is set (listed, estimated, 0 below
          rosterable depth, not priced), how many inputs stand behind each
          DDF Value version, and real examples of each case.
  Post 6  how many rostered players carry a one-source DDF Value, how far the
          four charts' Adjusted values spread for rostered players, and one
          worked Compare read (app/v2/trade.js dealRead, ported in
          tools/research/chart_agreement.py) with the per-chart split check.

Every figure is the 2026 season's published data as of the fixture's build
time and content week, recorded in run_meta.json. Nothing here changes a value.
"""
from __future__ import annotations

import itertools
import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "tools" / "research"))
sys.path.insert(0, str(REPO))
import value_reference as vr  # noqa: E402
import chart_agreement as ca  # noqa: E402  (the verified ports of trade.js)

OUT = REPO / "docs" / "research" / "data" / "posts04_06"
CHARTS = list(vr.PUBLISHED)
PROJS = list(vr.PROJECTIONS)
SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
DEFAULT = ("ppr", 12)          # the site's default setting (curve-widget.js)
ROSTERED = ("starter", "bench")


def load():
    inp = vr.Inputs.load()
    hist = vr.History(vr.HISTORY)
    week = vr.freshness(inp)["current_week"]
    div = vr.load_divergence_exclusions(week=week)
    return inp, hist, week, div


def setting(inp, hist, div, scoring, teams):
    return vr.Setting(inp, scoring, teams, hist=hist, divergence_exclusions=div)


def name(inp, pk):
    p = inp.players.get(pk) or {}
    return f'{p.get("name", pk)} ({p.get("pos", "?")})'


def pair_inversions(listed, before, after):
    """Pairs (i, j) the first scale orders strictly one way and the second the
    other way (ties on either side are not counted)."""
    n = 0
    for a, b in itertools.combinations(listed, 2):
        x = before[a] - before[b]
        y = after[a] - after[b]
        if x * y < 0:
            n += 1
    return n


# ---------------------------------------------------------------------------
# Post 4
# ---------------------------------------------------------------------------

def post4(inp, hist, div):
    factors = []
    for scoring in SCORINGS:
        for teams in TEAMS:
            s = setting(inp, hist, div, scoring, teams)
            res, st = s.result(), s.state()
            for c in CHARTS:
                ix = res["indexed"].get(c)
                if not ix:
                    factors.append({"scoring": scoring, "teams": teams, "chart": c, "factor": None,
                                    "why": st["excluded"].get(c, "no section")})
                    continue
                src = s._sources(st["current"])[c]
                listed = sorted(src.values, key=lambda i: (-src.values[i], i))
                top = listed[0] if listed else None
                factors.append({
                    "scoring": scoring, "teams": teams, "chart": c,
                    "included": c in st["included"] and c not in st["hidden"],
                    "factor": ix["factor"], "shared_players": ix["shared_players"],
                    "ddf_total": round(ix["ddf_total"], 1), "native_total": round(ix["native_total"], 1),
                    "top_player": name(inp, top) if top is not None else None,
                    "top_native": src.values.get(top), "top_rescaled":
                        round(src.values[top] * ix["factor"], 1) if top is not None and ix["factor"] else None,
                })

    # The default setting in detail: order kept by one factor, broken by a
    # per-position factor (the old method's shape, without its starter/bench
    # split, so the counterfactual is a lower bound on what the old method did).
    s = setting(inp, hist, div, *DEFAULT)
    res, st = s.result(), s.state()
    srcs = s._sources(st["current"])
    detail = []
    for c in CHARTS:
        ix = res["indexed"][c]
        if ix["factor"] is None:
            continue
        native = srcs[c].values
        listed = [i for i in native if i in res["rows"]]
        one = {i: native[i] * ix["factor"] for i in listed}
        ddf = {i: res["rows"][i]["ddf"]["blended"]["value"] for i in listed}
        by_pos = {}
        for p in vr.POSITIONS:
            shared = [i for i in listed if res["rows"][i]["pos"] == p and ddf[i] is not None]
            nt = sum(native[i] for i in shared)
            dt = sum(ddf[i] for i in shared)
            by_pos[p] = dt / nt if nt > 0 and dt > 0 else None
        per_pos = {i: native[i] * by_pos[res["rows"][i]["pos"]] for i in listed
                   if by_pos.get(res["rows"][i]["pos"])}
        kept = [i for i in listed if i in per_pos]
        pairs = len(kept) * (len(kept) - 1) // 2
        detail.append({
            "chart": c, "listed": len(listed), "factor": ix["factor"],
            "per_position_factors": by_pos,
            "one_factor_inversions": pair_inversions(listed, native, one),
            "per_position_inversions": pair_inversions(kept, native, per_pos),
            "pairs_checked": pairs,
        })

    # An example of the counterfactual: the chart and pair with the largest
    # native gap that a per-position factor flips.
    example = None
    for d in detail:
        c = d["chart"]
        native = srcs[c].values
        f = d["per_position_factors"]
        listed = [i for i in native if i in res["rows"] and f.get(res["rows"][i]["pos"])]
        listed.sort(key=lambda i: -native[i])
        for a, b in itertools.combinations(listed[:60], 2):
            pa, pb = res["rows"][a]["pos"], res["rows"][b]["pos"]
            if pa == pb or native[a] <= native[b]:
                continue
            if native[a] * f[pa] < native[b] * f[pb]:
                gap = native[a] / native[b]
                if example is None or gap > example["native_ratio"]:
                    example = {"chart": c, "higher": name(inp, a), "lower": name(inp, b),
                               "native": [native[a], native[b]], "native_ratio": round(gap, 3),
                               "one_factor": [round(native[a] * d["factor"], 1), round(native[b] * d["factor"], 1)],
                               "per_position": [round(native[a] * f[pa], 1), round(native[b] * f[pb], 1)]}
    return {"factors": factors, "default_detail": detail, "counterfactual_example": example}


# ---------------------------------------------------------------------------
# Post 5
# ---------------------------------------------------------------------------

def status_of(row, c):
    if row["estimated"].get(c):
        return "estimated"
    reason = row["reasons"].get(c) or ""
    if reason.startswith("Below rosterable depth"):
        return "zero_below_depth"
    if "doesn't price" in reason:
        return "not_priced_position"
    if row["adjusted"].get(c) is None:
        return "null_other"
    return "listed"


def post5(inp, hist, div):
    out = {}
    s = setting(inp, hist, div, *DEFAULT)
    res, st = s.result(), s.state()
    rows = res["rows"]
    out["rows"] = len(rows)
    out["included"] = st["included"]
    out["excluded"] = st["excluded"]
    out["hidden"] = sorted(st["hidden"])
    rostered = [i for i, r in rows.items() if r.get("ddf_tier") in ROSTERED]
    out["rostered"] = len(rostered)

    status = {c: Counter() for c in CHARTS}
    status_rostered = {c: Counter() for c in CHARTS}
    for i, r in rows.items():
        for c in CHARTS:
            k = status_of(r, c)
            status[c][k] += 1
            if i in rostered:
                status_rostered[c][k] += 1
    out["chart_row_status"] = {c: dict(v) for c, v in status.items()}
    out["chart_row_status_rostered"] = {c: dict(v) for c, v in status_rostered.items()}

    def counts(version, pool):
        return dict(sorted(Counter(rows[i]["ddf"][version]["count"] for i in pool).items()))
    out["ddf_input_count"] = {v: counts(v, rows) for v in ("blended", "projections")}
    out["ddf_input_count_rostered"] = {v: counts(v, rostered) for v in ("blended", "projections")}
    out["low_confidence"] = {v: sum(1 for r in rows.values() if r["ddf"][v]["low_confidence"])
                             for v in ("blended", "projections")}
    out["low_confidence_rostered"] = {v: sum(1 for i in rostered if rows[i]["ddf"][v]["low_confidence"])
                                      for v in ("blended", "projections")}
    out["no_value"] = {v: sum(1 for r in rows.values() if r["ddf"][v]["value"] is None)
                       for v in ("blended", "projections")}

    # Examples (deterministic: highest DDF Value first).
    by_value = sorted(rows, key=lambda i: (-(rows[i]["ddf"]["blended"]["value"] or -1), i))
    ex = {}
    for i in by_value:
        r = rows[i]
        st_c = {c: status_of(r, c) for c in CHARTS}
        if "estimated" in st_c.values() and "est" not in ex:
            c = next(c for c in CHARTS if st_c[c] == "estimated")
            ex["est"] = {"player": name(inp, i), "chart": c, "path": r["estimated"][c],
                         "reason": r["reasons"].get(c), "adjusted": r["adjusted"], "ddf": r["ddf"]["blended"]}
        if "zero_below_depth" in st_c.values() and "listed" in st_c.values() and r.get("ddf_tier") in ROSTERED \
                and "zero" not in ex:
            ex["zero"] = {"player": name(inp, i), "status": st_c, "adjusted": r["adjusted"],
                          "ddf": r["ddf"]["blended"], "ddf_projections": r["ddf"]["projections"],
                          "tier": r.get("ddf_tier")}
        if r["ddf"]["projections"]["count"] in (1, 2) and r["ddf"]["projections"]["value"] and "proj_gap" not in ex \
                and r.get("ddf_tier") in ROSTERED:
            ex["proj_gap"] = {"player": name(inp, i), "adjusted": {k: r["adjusted"].get(k) for k in PROJS},
                              "reasons": {k: r["reasons"].get(k) for k in PROJS},
                              "ddf_projections": r["ddf"]["projections"]}
        if r["ddf"]["projections"]["low_confidence"] and "one_projections" not in ex:
            ex["one_projections"] = {"player": name(inp, i), "ddf_projections": r["ddf"]["projections"],
                                     "ddf": r["ddf"]["blended"], "tier": r.get("ddf_tier"),
                                     "reasons": {k: r["reasons"].get(k) for k in PROJS}}
        if r["ddf"]["blended"]["low_confidence"] and "one" not in ex:
            ex["one"] = {"player": name(inp, i), "ddf": r["ddf"]["blended"], "tier": r.get("ddf_tier"),
                         "reasons": {c: r["reasons"].get(c) for c in CHARTS}}
    zero_all = [i for i in rows if rows[i]["ddf"]["blended"]["value"] == 0.0]
    out["ddf_value_zero"] = len(zero_all)
    none = [i for i in rows if rows[i]["ddf"]["blended"]["value"] is None]
    if none:
        i = sorted(none)[0]
        ex["none"] = {"player": name(inp, i), "reasons": {c: rows[i]["reasons"].get(c) for c in CHARTS},
                      "ddf_projections": rows[i]["ddf"]["projections"]}
    out["examples"] = ex

    # Per scoring at 12 teams: how often each case fires (Standard, Half, PPR).
    out["by_scoring"] = {}
    for scoring in SCORINGS:
        s2 = setting(inp, hist, div, scoring, 12)
        r2 = s2.result()["rows"]
        rost = [i for i, r in r2.items() if r.get("ddf_tier") in ROSTERED]
        est = sum(1 for i in rost for c in CHARTS if r2[i]["estimated"].get(c))
        zero = sum(1 for i in rost for c in CHARTS if status_of(r2[i], c) == "zero_below_depth")
        out["by_scoring"][scoring] = {
            "rostered": len(rost),
            "rostered_one_source": sum(1 for i in rost if r2[i]["ddf"]["blended"]["low_confidence"]),
            "rostered_chart_cells_estimated": est,
            "rostered_chart_cells_zero_below_depth": zero,
            "rostered_chart_cells": len(rost) * len(CHARTS),
        }
    return out


# ---------------------------------------------------------------------------
# Post 6
# ---------------------------------------------------------------------------

def quantile(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def post6(inp, hist, div):
    out = {}
    s = setting(inp, hist, div, *DEFAULT)
    res, st = s.result(), s.state()
    rows = res["rows"]
    rostered = [i for i, r in rows.items() if r.get("ddf_tier") in ROSTERED]
    spread = {p: [] for p in vr.POSITIONS}
    for i in rostered:
        vals = [rows[i]["adjusted"][c] for c in CHARTS if rows[i]["adjusted"].get(c) is not None]
        if len(vals) >= 2:
            spread[rows[i]["pos"]].append(max(vals) - min(vals))
    out["chart_spread_rostered"] = {p: {"n": len(v), "median": round(quantile(v, 0.5), 1) if v else None,
                                        "p90": round(quantile(v, 0.9), 1) if v else None}
                                    for p, v in spread.items()}
    out["rostered_by_input_count"] = dict(sorted(Counter(rows[i]["ddf"]["blended"]["count"] for i in rostered).items()))

    # A worked Compare read: the 1-for-1 between two rostered starters closest
    # on DDF Value whose four chart nets do not all point the same way.
    chart_keys = [c for c in CHARTS if c in st["included"] and c not in st["hidden"]]
    prow = ca.rows_from_result(res, inp)
    starters = sorted((i for i in rostered if rows[i].get("ddf_tier") == "starter"
                       and all(ca.finite(prow[i]["values"].get(k)) for k in chart_keys + [ca.DDF, ca.PROJ])),
                      key=lambda i: (-prow[i]["values"][ca.DDF], i))[:60]
    best = None
    for a, b in itertools.combinations(starters, 2):
        give, receive = [prow[b]], [prow[a]]   # a is the higher DDF Value: receive him
        deal = ca.deal_read(give, receive, chart_keys)
        if deal["kind"] != "read" or deal["value"]["side"] != "win":
            continue
        crow = [r for r in ca.compare_trade(give, receive, chart_keys) if r["net"] is not None]
        signs = {ca.sign_of(r["net"]) for r in crow}
        if len(signs) < 2:
            continue
        net = deal["value"]["net"]
        if best is None or abs(net) < abs(best[0]):
            best = (net, a, b, deal, crow)
    if best:
        net, a, b, deal, crow = best
        yes = sum(1 for r in crow if ca.sign_of(r["net"]) <= 0)
        of = len(crow)
        accept = "Likely" if yes / of >= 2 / 3 else "Unlikely" if yes / of <= 1 / 3 else "Toss-up"
        split = accept != {"win": "Unlikely", "even": "Likely", "lose": "Likely"}[deal["market"]["side"]]
        out["worked_trade"] = {
            "give": name(inp, b), "receive": name(inp, a), "charts": chart_keys,
            "ddf_value": {"give": round(prow[b]["values"][ca.DDF], 1), "receive": round(prow[a]["values"][ca.DDF], 1),
                          "net": round(deal["value"]["net"], 1), "side": deal["value"]["side"]},
            "projections": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in deal["projections"].items()},
            "market": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in deal["market"].items()},
            "chart_nets": {r["key"]: round(r["net"], 1) for r in crow},
            "charts_other_manager_wins_or_even": f"{yes} of {of}", "accept_count_answer": accept,
            "split_read": split, "cell": deal["cell"],
            "one_source_in_trade": prow[a]["low_confidence"] or prow[b]["low_confidence"],
            "raw_ddf_net": deal["value"]["net"],
            "site_deal_read": site_deal_read(prow[b], prow[a], chart_keys),
        }
    return out


NODE_DEAL = r"""
const fs = require("fs");
const TC = require(process.argv[2]);
const t = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const d = TC.dealRead([t.give], [t.receive], t.chartKeys);
fs.writeFileSync(process.argv[4], JSON.stringify({kind: d.kind, cell: d.cell, title: d.title, action: d.action,
  text: d.text, production: d.production, split: d.market && d.market.split}));
"""


def site_deal_read(give, receive, chart_keys):
    """The worked trade through the site's own app/v2/trade.js dealRead (node),
    so the post quotes the read the page shows, split and production included."""
    node = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
    if not node:
        return {"ran": False, "why": "node not found"}
    js_row = lambda r: {"player_key": r["player_key"], "values": {k: v for k, v in r["values"].items() if ca.finite(v)}}
    with tempfile.TemporaryDirectory() as tmp:
        inp, outp, script = Path(tmp) / "in.json", Path(tmp) / "out.json", Path(tmp) / "deal.js"
        inp.write_text(json.dumps({"give": js_row(give), "receive": js_row(receive), "chartKeys": chart_keys}))
        script.write_text(NODE_DEAL)
        r = subprocess.run([node, str(script), str(REPO / "app" / "v2" / "trade.js"), str(inp), str(outp)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            return {"ran": False, "why": r.stderr[-500:]}
        return {"ran": True, **json.loads(outp.read_text())}


def main() -> int:
    inp, hist, week, div = load()
    OUT.mkdir(parents=True, exist_ok=True)
    meta = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "fixture_built_at": inp.fixture.get("built_at"), "content_week": week, "season": 2026,
            "data_label": "published (2026 season, current content week)",
            "default_setting": {"scoring": DEFAULT[0], "teams": DEFAULT[1]},
            "engine": "pipelines/value_reference.py", "pipeline_version": vr.PIPELINE_VERSION,
            "divergence_exclusions": sorted(div)}
    p4, p5, p6 = post4(inp, hist, div), post5(inp, hist, div), post6(inp, hist, div)
    for fname, obj in (("run_meta.json", meta), ("post04.json", p4), ("post05.json", p5), ("post06.json", p6)):
        (OUT / fname).write_text(json.dumps(obj, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} (week {week}, fixture {meta['fixture_built_at']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
