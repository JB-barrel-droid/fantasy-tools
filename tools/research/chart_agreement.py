#!/usr/bin/env python3
"""Research post 8 (JEG-883): when do the trade charts agree, and does
agreement mean anything?

One command, reproducible, standard library plus numpy:

  python3 tools/research/chart_agreement.py            # writes docs/research/data/post8/
  python3 tools/research/chart_agreement.py --quick    # fewer trades, for a smoke run

What it does
  1. Rebuilds the page's rows for every saved content week (data/history
     week-2 .. week-7) with the Python reference engine
     (pipelines/value_reference.py, run_pipeline on each week's saved natives,
     default setting PPR / 12 teams / QB1 RB2 WR2 TE1 FLEX1 BENCH7), and the
     live week with the build's own holds (Setting), so the live chart count
     matches what the page shows this week.
  2. Ports the site's verdict rules, line for line, from app/v2/trade.js
     (compareTrade, tradeVerdict, tradeHeadlines, dealRead) and
     app/v2/finder.js (findTrades' acceptance rule). `--verify-port` runs the
     same trades through the real JavaScript in node and diffs every label.
  3. Builds a large, seeded set of plausible trades (1-for-1, 2-for-1, 2-for-2,
     3-for-2) from rostered players (the engine's own ddf_tier, not waiver),
     with the two sides within 20% of each other on DDF Value, evaluates them
     in the week they were drawn and again the next week, and writes every
     table the post quotes.

Outputs (docs/research/data/post8/): run_meta.json, labels.csv,
pairwise_rank_corr.csv, pairwise_direction.csv, stability.csv,
high_by_agree.csv, thresholds.csv, bootstrap.json, port_check.json, summary.md.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))
import value_reference as vr  # noqa: E402

OUT = REPO / "docs" / "research" / "data" / "post8"
HISTORY = REPO / "data" / "history"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]   # finder.js CHART_KEYS, targets.js CHART_KEYS
DDF = "ddf_value"
PROJ = "ddf_value_projections"
SHAPES = [(1, 1), (2, 1), (2, 2), (3, 2)]
SETTING = {"scoring": "ppr", "teams": 12, "superflex": 0}     # curve-widget.js lines 294-295
BALANCE = 0.20          # |net| / value traded, the plausibility band for sampled trades
SEED = 883

# ---------------------------------------------------------------------------
# The site's rules, ported from app/v2/trade.js and app/v2/finder.js.
# Each function names the lines it mirrors. Rows are {key: value-or-None}.
# ---------------------------------------------------------------------------
THIN_MARGIN = 0.05                 # trade.js:168
MIN_DEAL_CHARTS = 3                # trade.js:280
FINDER_MIN_CHARTS = 3              # finder.js:24
LEVELS = ["Low", "Medium", "High"]  # trade.js:169


def finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def sign_of(net):                  # trade.js:91 (and :63, finder.js:30): 0.0 as shown points neither way
    return 0 if abs(net) < 0.05 else (1 if net > 0 else -1)


def compare_trade(give, receive, keys):   # trade.js:24-43
    rows = []
    for key in keys:
        missing = 0
        give_sum = receive_sum = 0.0
        for row in give:
            v = row["values"].get(key)
            if finite(v):
                give_sum += v
            else:
                missing += 1
        for row in receive:
            v = row["values"].get(key)
            if finite(v):
                receive_sum += v
            else:
                missing += 1
        if missing:
            rows.append({"key": key, "give": None, "receive": None, "net": None, "missing": missing})
        else:
            rows.append({"key": key, "give": give_sum, "receive": receive_sum, "net": receive_sum - give_sum, "missing": 0})
    return rows


def trade_verdict(rows, key):            # trade.js:136-151
    head = next((r for r in rows if r["key"] == key), None)
    if head is None:
        return {"kind": None}
    others = [r for r in rows if r["key"] != key]
    complete = [r for r in others if r["net"] is not None]
    where = lambda want: [r["key"] for r in complete if sign_of(r["net"]) == want]
    base = {"upKeys": where(1), "downKeys": where(-1), "evenKeys": where(0), "others": len(complete)}
    if head["net"] is None:
        return {"kind": "incomplete", "agreeKeys": [], "againstKeys": [], **base}
    s = sign_of(head["net"])
    kind = "win" if s > 0 else "lose" if s < 0 else "even"
    against = base["downKeys"] if s > 0 else base["upKeys"] if s < 0 else []
    agree = base["upKeys"] if s > 0 else base["downKeys"] if s < 0 else base["evenKeys"]
    return {"kind": kind, "net": head["net"], "agreeKeys": agree, "againstKeys": against, **base}


def side_of(net, give, receive):         # trade.js:302-305
    threshold = max(1.0, 0.03 * ((give + receive) / 2))
    return "win" if net >= threshold else "lose" if net <= -threshold else "even"


def deal_read(give, receive, chart_keys):   # trade.js:316-345
    v, p = compare_trade(give, receive, [DDF, PROJ])
    def net(row):
        if row["net"] is None:
            return {"net": None, "give": None, "receive": None, "side": None}
        return {"net": row["net"], "give": row["give"], "receive": row["receive"], "side": side_of(row["net"], row["give"], row["receive"])}
    chart_rows = compare_trade(give, receive, chart_keys) if chart_keys else []
    complete = [r for r in chart_rows if r["net"] is not None]
    if len(complete) < MIN_DEAL_CHARTS:
        market = {"net": None, "side": None, "tooFew": True, "chartCount": len(complete)}
    else:
        avg_net = sum(r["net"] for r in complete) / len(complete)
        avg_give = sum(r["give"] for r in complete) / len(complete)
        avg_rec = sum(r["receive"] for r in complete) / len(complete)
        market = {"net": avg_net, "side": side_of(avg_net, avg_give, avg_rec), "tooFew": False, "chartCount": len(complete)}
    out = {"value": net(v), "market": market, "projections": net(p)}
    if out["value"]["net"] is None:
        return {"kind": "incomplete", "cell": None, "why": "no DDF Value", **out}
    if market["tooFew"]:
        return {"kind": "incomplete", "cell": None, "why": "too few charts", **out}
    return {"kind": "read", "cell": f'{out["value"]["side"]}|{out["market"]["side"]}', **out}


def lowered(level):                      # trade.js:170
    return LEVELS[max(0, LEVELS.index(level) - 1)]


def capped(level, cap):                  # trade.js:171
    return LEVELS[min(LEVELS.index(level), LEVELS.index(cap))]


def trade_headlines(rows, key, chart_keys, low_confidence, deal):   # trade.js:172-240
    head = next((r for r in rows if r["key"] == key), None)
    traded = head["give"] + head["receive"] if head and head["net"] is not None else None
    thin = traded is not None and (traded <= 0 or abs(head["net"]) < THIN_MARGIN * traded)
    margin = abs(head["net"]) / traded if traded and traded > 0 else None
    level_for = lambda share: "High" if share >= 0.75 else "Medium" if share >= 0.6 else "Low"
    v = trade_verdict(rows, key)
    chart_set = set(chart_keys)
    chart_agree = len([k for k in v.get("agreeKeys", []) if k in chart_set])
    chart_total = len([r for r in rows if r["key"] in chart_set and r["net"] is not None]) if v.get("others") is not None else 0
    if head is None or v["kind"] in (None, "incomplete"):
        propose = {"answer": None, "confidence": None, "agree": chart_agree, "of": chart_total, "margin": margin, "reason": "no DDF Value"}
    elif not deal or deal["kind"] != "read":
        propose = {"answer": "Unclear", "confidence": "Low", "agree": chart_agree, "of": chart_total, "margin": margin, "reason": "no deal read"}
    else:
        v_side = deal["value"]["side"]
        p = deal["projections"]
        p_side = p["side"] if p["net"] is not None else None
        p_traded = p["give"] + p["receive"] if p["give"] is not None else None
        p_margin = abs(p["net"]) / p_traded if p_traded and p_traded > 0 and p["net"] is not None else None
        if v_side == "win" and p_side == "win" and not thin:
            answer, level, reason = "Yes", ("High" if p_margin is not None and p_margin >= THIN_MARGIN else "Medium"), "both win"
        elif v_side == "lose" and p_side == "lose" and not thin:
            answer, level, reason = "No", ("High" if p_margin is not None and p_margin >= THIN_MARGIN else "Medium"), "both lose"
        else:
            answer, level = "Unclear", "Low"
            reason = "thin" if thin else "no projections" if p_side is None else "projections disagree" if p_side != v_side else "even"
        if low_confidence:
            level = lowered(level)
        propose = {"answer": answer, "confidence": level, "agree": chart_agree, "of": chart_total, "margin": margin, "reason": reason}
    charts = [r for r in rows if r["key"] in chart_set and r["net"] is not None]
    if not charts:
        accept = {"answer": None, "confidence": None, "yes": 0, "of": 0}
    else:
        yes = len([r for r in charts if sign_of(r["net"]) <= 0])
        share = yes / len(charts)
        answer = "Likely" if share >= 2 / 3 else "Unlikely" if share <= 1 / 3 else "Toss-up"
        same = yes if answer == "Likely" else len(charts) - yes if answer == "Unlikely" else max(yes, len(charts) - yes)
        level = level_for(same / len(charts))
        if len(charts) < 3:
            level = capped(level, "Medium")
        if thin:
            level = "Low"
        accept = {"answer": answer, "confidence": level, "yes": yes, "of": len(charts)}
    return {"propose": propose, "accept": accept}


def finder_ok(give, receive, chart_keys):   # finder.js:59-121 (the acceptance rule, not the search)
    min_charts = min(FINDER_MIN_CHARTS, len(chart_keys))
    ddf = compare_trade(give, receive, [DDF])[0]
    if ddf["net"] is None or sign_of(ddf["net"]) <= 0:
        return False
    priced = ok = 0
    for r in compare_trade(give, receive, chart_keys):
        if r["net"] is None:
            continue
        priced += 1
        if sign_of(r["net"]) <= 0:
            ok += 1
    return priced >= min_charts and ok >= min_charts


def evaluate(give, receive, chart_keys, ddf_key=DDF):
    """Everything the page says about one trade, with DDF Value read from
    ddf_key (ddf_value today; ddf_value_projections once PR #814 merges)."""
    if ddf_key != DDF:
        give = [{**r, "values": {**r["values"], DDF: r["values"].get(ddf_key)}} for r in give]
        receive = [{**r, "values": {**r["values"], DDF: r["values"].get(ddf_key)}} for r in receive]
    rows = compare_trade(give, receive, [DDF] + chart_keys)
    low = any(r["low_confidence"] for r in give + receive)
    deal = deal_read(give, receive, chart_keys)
    head = trade_headlines(rows, DDF, chart_keys, low, deal)
    chart_signs = {r["key"]: (None if r["net"] is None else sign_of(r["net"])) for r in rows if r["key"] != DDF}
    ddf_row = rows[0]
    return {"propose": head["propose"], "accept": head["accept"], "deal": deal["cell"], "deal_kind": deal["kind"],
            "ddf_sign": None if ddf_row["net"] is None else sign_of(ddf_row["net"]),
            "ddf_net": ddf_row["net"], "margin": head["propose"]["margin"],
            "proj_sign": None if deal["projections"]["net"] is None else sign_of(deal["projections"]["net"]),
            "chart_signs": chart_signs, "finder": finder_ok(give, receive, chart_keys)}


# ---------------------------------------------------------------------------
# Rows per week from the reference engine
# ---------------------------------------------------------------------------

def load_inputs():
    inp = vr.Inputs.load()
    hist = vr.History(HISTORY)
    return inp, hist


def week_rows(inp, hist, week, base_setting):
    """The page's rows (indexed charts, DDF versions, tier, low-confidence flag)
    for one saved week, every complete saved source included (the holds a
    week carried at the time are not saved with it)."""
    doc = hist.week_doc(week)
    if not doc:
        return None, []
    natives = {}
    for src, entry in doc["sources"].items():
        if src not in vr.SOURCES or not entry.get("complete"):
            continue
        nat = vr.snapshot_natives(inp, src, entry, base_setting.scoring)
        if nat:
            natives[src] = nat
    res = vr.run_pipeline(base_setting.league, base_setting._sources(natives), base_setting.pos_of,
                          list(natives), None, lineup=base_setting.lineup, hidden=set())
    return rows_from_result(res, inp), [k for k in CHARTS if k in natives]


def rows_from_result(res, inp):
    out = {}
    for pk, r in res["rows"].items():
        values = {k: r["indexed"].get(k) for k in CHARTS}
        values[DDF] = r["ddf"]["blended"]["value"]
        values[PROJ] = r["ddf"]["projections"]["value"]
        values["ddf_value_charts"] = r["ddf"]["charts"]["value"]
        out[pk] = {"player_key": pk, "pos": inp.players[pk]["pos"], "values": values,
                   "tier": r.get("ddf_tier"), "low_confidence": bool(r["ddf"]["blended"]["low_confidence"])}
    return out


def live_rows(inp, hist):
    """This week as the page shows it: the build's holds decide which charts
    Compare and the finder can read (JEG-819: a held source is not available)."""
    s = vr.Setting(inp, SETTING["scoring"], SETTING["teams"], SETTING["superflex"], hist=hist)
    st = s.state()
    available = [k for k in CHARTS if k in st["included"] and k not in st["hidden"]]
    return rows_from_result(s.result(), inp), available, st, s


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def sample_trades(rows, n_per_shape, rng):
    """Plausible trades: rostered players (ddf_tier starter or bench), every
    player priced by DDF Value, sides within BALANCE of each other."""
    pool = [r for r in rows.values() if r["tier"] in ("starter", "bench") and finite(r["values"][DDF]) and r["values"][DDF] > 0]
    pool.sort(key=lambda r: -r["values"][DDF])
    keys = [r["player_key"] for r in pool]
    value = {r["player_key"]: r["values"][DDF] for r in pool}
    trades = []
    for g, rcv in SHAPES:
        got = 0
        tries = 0
        while got < n_per_shape and tries < n_per_shape * 200:
            tries += 1
            picked = rng.sample(keys, g + rcv)
            give, receive = picked[:g], picked[g:]
            gs, rs = sum(value[k] for k in give), sum(value[k] for k in receive)
            traded = gs + rs
            if traded <= 0 or abs(rs - gs) / traded > BALANCE:
                continue
            trades.append({"shape": f"{g}-for-{rcv}", "give": sorted(give), "receive": sorted(receive)})
            got += 1
    return trades


def trade_rows(trade, rows):
    give = [rows.get(k) for k in trade["give"]]
    receive = [rows.get(k) for k in trade["receive"]]
    if any(r is None for r in give + receive):
        return None, None
    return give, receive


def tier_class(give, receive):
    tiers = {r["tier"] for r in give + receive}
    return "all starters" if tiers == {"starter"} else "all bench" if tiers == {"bench"} else "mixed"


def pos_class(give, receive):
    pos = {r["pos"] for r in give + receive}
    return next(iter(pos)) + " only" if len(pos) == 1 else "mixed positions"


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def spearman(x, y):
    if len(x) < 3:
        return None
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    # ties are rare in these values; plain rank correlation
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def boot_ci(flags, rng, n=2000):
    a = np.asarray(flags, dtype=float)
    if a.size == 0:
        return None
    idx = rng.integers(0, a.size, size=(n, a.size))
    means = a[idx].mean(axis=1)
    return [float(a.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)), int(a.size)]


def pct(x, d=1):
    return f"{100 * x:.{d}f}%"


# ---------------------------------------------------------------------------
# Port check in node against the real trade.js / finder.js
# ---------------------------------------------------------------------------
NODE_CHECK = r"""
const fs = require("fs");
const TC = require(process.argv[2]);
const TF = require(process.argv[3]);
const input = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
const out = [];
for (const t of input.trades) {
  const rows = input.rows;
  const give = t.give.map(k => rows[k]); const receive = t.receive.map(k => rows[k]);
  const keys = ["ddf_value"].concat(t.chartKeys);
  const points = TC.compareTrade(give, receive, keys).rows;
  const low = give.concat(receive).some(r => r.ddfLowConfidence);
  const deal = TC.dealRead(give, receive, t.chartKeys);
  const h = TC.tradeHeadlines(points, "ddf_value", {chartKeys: t.chartKeys, lowConfidence: low, deal});
  // finder: one package each side, so findTrades either lists this trade or not.
  const f = TF.findTrades(give, receive, {chartKeys: t.chartKeys, maxSize: Math.max(give.length, receive.length), limit: 1000});
  const listed = f.trades.some(x => x.give.length === give.length && x.receive.length === receive.length
    && x.give.every(r => give.includes(r)) && x.receive.every(r => receive.includes(r)));
  out.push({propose: h.propose.answer, proposeConf: h.propose.confidence, agree: h.propose.agree, of: h.propose.of,
    accept: h.accept.answer, acceptConf: h.accept.confidence, yes: h.accept.yes, deal: deal.kind === "read" ? deal.cell : null, finder: listed});
}
fs.writeFileSync(process.argv[5], JSON.stringify(out));
"""


def verify_port(rows, chart_keys, trades, evals, k):
    node = subprocess.run(["which", "node"], capture_output=True, text=True).stdout.strip()
    if not node:
        return {"ran": False, "why": "node not found"}
    pick = list(range(0, len(trades), max(1, len(trades) // k)))[:k]
    js_rows = {str(pk): {"player_key": pk, "values": {kk: v for kk, v in r["values"].items() if finite(v)},
                         "ddfLowConfidence": r["low_confidence"]} for pk, r in rows.items()}
    payload = {"rows": js_rows, "trades": [{"give": [str(x) for x in trades[i]["give"]], "receive": [str(x) for x in trades[i]["receive"]],
                                            "chartKeys": chart_keys} for i in pick]}
    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "in.json"; outp = Path(tmp) / "out.json"; script = Path(tmp) / "check.js"
        inp.write_text(json.dumps(payload)); script.write_text(NODE_CHECK)
        r = subprocess.run([node, str(script), str(REPO / "app" / "v2" / "trade.js"), str(REPO / "app" / "v2" / "finder.js"),
                            str(inp), str(outp)], capture_output=True, text=True)
        if r.returncode != 0:
            return {"ran": False, "why": r.stderr[-500:]}
        js = json.loads(outp.read_text())
    mismatches = []
    for i, j in zip(pick, js):
        e = evals[i]
        mine = {"propose": e["propose"]["answer"], "proposeConf": e["propose"]["confidence"], "agree": e["propose"]["agree"],
                "of": e["propose"]["of"], "accept": e["accept"]["answer"], "acceptConf": e["accept"]["confidence"],
                "yes": e["accept"]["yes"], "deal": e["deal"], "finder": e["finder"]}
        if mine != j:
            mismatches.append({"trade": trades[i], "python": mine, "node": j})
    return {"ran": True, "compared": len(pick), "mismatches": len(mismatches), "examples": mismatches[:5],
            "fields": ["propose", "proposeConf", "agree", "of", "accept", "acceptConf", "yes", "deal", "finder"]}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_csv(path, header, rows):
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--per-shape", type=int, default=3000, help="trades per shape per week")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--verify-port", action="store_true", default=True)
    ap.add_argument("--port-trades", type=int, default=400)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    per_shape = 300 if args.quick else args.per_shape
    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    nrng = np.random.default_rng(SEED)

    inp, hist = load_inputs()
    live, live_charts, live_state, base = live_rows(inp, hist)
    weeks = sorted(int(w) for w in (hist.index.get("weeks") or {}))
    rows_by_week, charts_by_week = {}, {}
    for w in weeks:
        rows, charts = week_rows(inp, hist, w, base)
        if rows:
            rows_by_week[w], charts_by_week[w] = rows, charts
    weeks = sorted(rows_by_week)
    git = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = {"script": "tools/research/chart_agreement.py", "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "engine": f"pipelines/value_reference.py {vr.VERSION} at git {git}", "setting": SETTING, "seed": SEED,
            "balance_band": BALANCE, "per_shape_per_week": per_shape, "weeks": weeks,
            "charts_saved_by_week": charts_by_week,
            "live": {"content_week": live_state["current_week"], "charts_available": live_charts,
                     "excluded": live_state["excluded"], "fixture_built_at": inp.fixture.get("built_at")},
            "players_by_week": {w: len(r) for w, r in rows_by_week.items()},
            "rostered_by_week": {w: sum(1 for r in rows.values() if r["tier"] in ("starter", "bench")) for w, rows in rows_by_week.items()}}

    # ---- trades: drawn in week W, evaluated in W and W+1 -------------------
    trades_by_week = {w: sample_trades(rows_by_week[w], per_shape, rng) for w in weeks}
    records = []   # one per (trade, evaluation week, ddf variant)
    for w in weeks:
        for t in trades_by_week[w]:
            give, receive = trade_rows(t, rows_by_week[w])
            base_rec = {"drawn": w, "shape": t["shape"], "tier": tier_class(give, receive), "pos": pos_class(give, receive),
                        "give": t["give"], "receive": t["receive"]}
            for variant, key in (("blended", DDF), ("projections", PROJ)):
                ev = evaluate(give, receive, charts_by_week[w], key)
                nxt = None
                if w + 1 in rows_by_week:
                    g2, r2 = trade_rows(t, rows_by_week[w + 1])
                    if g2:
                        nxt = evaluate(g2, r2, charts_by_week[w + 1], key)
                records.append({**base_rec, "variant": variant, "now": ev, "next": nxt})

    # ---- 1. label frequencies ------------------------------------------------
    label_rows = []
    for variant in ("blended", "projections"):
        for w in weeks:
            recs = [r for r in records if r["variant"] == variant and r["drawn"] == w]
            n = len(recs)
            c_prop = Counter(f'{r["now"]["propose"]["answer"]} / {r["now"]["propose"]["confidence"]}' for r in recs)
            c_acc = Counter(f'{r["now"]["accept"]["answer"]} / {r["now"]["accept"]["confidence"]}' for r in recs)
            c_deal = Counter(str(r["now"]["deal"]) for r in recs)
            c_agree = Counter(f'{r["now"]["propose"]["agree"]} of {r["now"]["propose"]["of"]}' for r in recs)
            c_why = Counter(f'{r["now"]["propose"]["answer"]}: {r["now"]["propose"]["reason"]}' for r in recs)
            finder = sum(1 for r in recs if r["now"]["finder"])
            for kind, counter in (("propose", c_prop), ("accept", c_acc), ("deal", c_deal), ("charts agree", c_agree), ("propose reason", c_why)):
                for label, cnt in sorted(counter.items()):
                    label_rows.append([variant, w, kind, label, cnt, n, round(cnt / n, 4)])
            label_rows.append([variant, w, "finder rule", "listed", finder, n, round(finder / n, 4)])
    write_csv(args.out / "labels.csv", ["ddf_variant", "week", "line", "label", "count", "trades", "share"], label_rows)

    # ---- 2a. pairwise rank correlation by week, position, tier ---------------
    corr_rows = []
    for w in weeks:
        rows = rows_by_week[w]
        for a, b in itertools.combinations(charts_by_week[w], 2):
            for group, pred in [("all", lambda r: True)] + [(p, (lambda p: lambda r: r["pos"] == p)(p)) for p in ("QB", "RB", "WR", "TE")] \
                    + [(t, (lambda t: lambda r: r["tier"] == t)(t)) for t in ("starter", "bench")]:
                xs, ys = [], []
                for r in rows.values():
                    va, vb = r["values"].get(a), r["values"].get(b)
                    if pred(r) and finite(va) and finite(vb) and (va > 0 or vb > 0):
                        xs.append(va); ys.append(vb)
                rho = spearman(np.array(xs), np.array(ys)) if xs else None
                corr_rows.append([w, a, b, group, len(xs), None if rho is None else round(rho, 4)])
    write_csv(args.out / "pairwise_rank_corr.csv", ["week", "chart_a", "chart_b", "group", "players_both_price", "spearman"], corr_rows)

    # ---- 2b. pairwise trade-direction agreement ------------------------------
    dir_rows = []
    blended = [r for r in records if r["variant"] == "blended"]
    pairs = list(itertools.combinations(CHARTS, 2)) + [(DDF, c) for c in CHARTS]
    for a, b in pairs:
        for group_name, keyf in (("shape", lambda r: r["shape"]), ("tier", lambda r: r["tier"]), ("pos", lambda r: r["pos"]), ("all", lambda r: "all")):
            groups = defaultdict(list)
            for r in blended:
                sa = r["now"]["ddf_sign"] if a == DDF else r["now"]["chart_signs"].get(a)
                sb = r["now"]["chart_signs"].get(b)
                if sa is None or sb is None or sa == 0 or sb == 0:
                    continue
                groups[keyf(r)].append(sa == sb)
            for g, flags in sorted(groups.items()):
                dir_rows.append([a, b, group_name, g, len(flags), round(sum(flags) / len(flags), 4)])
    write_csv(args.out / "pairwise_direction.csv", ["series_a", "series_b", "group_kind", "group", "trades_both_point", "same_direction"], dir_rows)

    # ---- 3. High confidence by chart-agreement count; next-week flips --------
    def flipped(r, what):
        if r["next"] is None:
            return None
        if what == "propose":
            return r["next"]["propose"]["answer"] != r["now"]["propose"]["answer"]
        if what == "ddf_sign":
            return r["next"]["ddf_sign"] is not None and r["now"]["ddf_sign"] is not None and r["next"]["ddf_sign"] != r["now"]["ddf_sign"]
        if what == "accept":
            return r["next"]["accept"]["answer"] != r["now"]["accept"]["answer"]
        if what == "deal":
            return r["next"]["deal"] != r["now"]["deal"]
        if what == "reversed":   # a Yes that becomes a No, or the reverse
            a, b = r["now"]["propose"]["answer"], r["next"]["propose"]["answer"]
            return {a, b} == {"Yes", "No"}
        raise ValueError(what)

    high_rows = []
    boot = {}
    for variant in ("blended", "projections"):
        recs = [r for r in records if r["variant"] == variant and r["next"] is not None]
        for answer in ("Yes", "No", "Unclear"):
            for conf in ("High", "Medium", "Low"):
                for agree in ("0", "1", "2", "3", "4", "any"):
                    sub = [r for r in recs if r["now"]["propose"]["answer"] == answer and r["now"]["propose"]["confidence"] == conf
                           and (agree == "any" or str(r["now"]["propose"]["agree"]) == agree)]
                    if not sub:
                        continue
                    ci_prop = boot_ci([flipped(r, "propose") for r in sub], nrng, 500)
                    ci_sign = boot_ci([flipped(r, "ddf_sign") for r in sub], nrng, 500)
                    ci_rev = boot_ci([flipped(r, "reversed") for r in sub], nrng, 500)
                    proj_agree = np.mean([r["now"]["proj_sign"] == r["now"]["ddf_sign"] for r in sub if r["now"]["proj_sign"] is not None]) if any(r["now"]["proj_sign"] is not None for r in sub) else None
                    high_rows.append([variant, answer, conf, agree, len(sub), round(ci_prop[0], 4), round(ci_prop[1], 4), round(ci_prop[2], 4),
                                      round(ci_sign[0], 4), round(ci_sign[1], 4), round(ci_sign[2], 4), round(ci_rev[0], 4),
                                      None if proj_agree is None else round(float(proj_agree), 4)])
                    if agree == "any":
                        boot[f"{variant}|{answer}|{conf}"] = {"propose_flip": ci_prop, "ddf_sign_flip": ci_sign, "reversed": ci_rev}
    write_csv(args.out / "high_by_agree.csv", ["ddf_variant", "propose", "confidence", "charts_agree", "trades_with_next_week",
                                               "propose_flip", "flip_lo95", "flip_hi95", "ddf_sign_flip", "sign_lo95", "sign_hi95",
                                               "reversed_next_week", "projections_same_sign_now"], high_rows)

    # ---- 3b. High labels: flips by package size, tier and position ----------
    grp_rows = []
    recs = [r for r in records if r["variant"] == "blended" and r["next"] is not None]
    for answer in ("Yes", "No"):
        for kind in ("shape", "tier", "pos"):
            groups = defaultdict(list)
            for r in recs:
                if r["now"]["propose"]["answer"] == answer and r["now"]["propose"]["confidence"] == "High":
                    groups[r[kind]].append(r)
            for g, sub in sorted(groups.items()):
                ci = boot_ci([flipped(r, "propose") for r in sub], nrng, 500)
                sign = float(np.mean([flipped(r, "ddf_sign") for r in sub]))
                agree4 = float(np.mean([r["now"]["propose"]["agree"] == r["now"]["propose"]["of"] for r in sub]))
                grp_rows.append([answer, kind, g, len(sub), round(ci[0], 4), round(ci[1], 4), round(ci[2], 4), round(sign, 4), round(agree4, 4)])
    write_csv(args.out / "high_by_group.csv", ["propose", "group_kind", "group", "trades_with_next_week", "propose_flip", "lo95", "hi95",
                                               "ddf_sign_flip", "all_charts_agree_share"], grp_rows)

    # ---- 4. stability by week pair and label, each series' own flips ---------
    stab_rows = []
    for variant in ("blended", "projections"):
        for w in weeks:
            recs = [r for r in records if r["variant"] == variant and r["drawn"] == w and r["next"] is not None]
            if not recs:
                continue
            n = len(recs)
            row = [variant, w, w + 1, n]
            for what in ("propose", "accept", "deal", "ddf_sign", "reversed"):
                row.append(round(float(np.mean([flipped(r, what) for r in recs])), 4))
            for c in CHARTS:
                both = [(r["now"]["chart_signs"].get(c), r["next"]["chart_signs"].get(c)) for r in recs]
                both = [(a, b) for a, b in both if a not in (None, 0) and b not in (None, 0)]
                row.append(round(float(np.mean([a != b for a, b in both])), 4) if both else None)
            proj = [(r["now"]["proj_sign"], r["next"]["proj_sign"]) for r in recs]
            proj = [(a, b) for a, b in proj if a not in (None, 0) and b not in (None, 0)]
            row.append(round(float(np.mean([a != b for a, b in proj])), 4) if proj else None)
            stab_rows.append(row)
    write_csv(args.out / "stability.csv", ["ddf_variant", "week", "next_week", "trades", "propose_flip", "accept_flip", "deal_flip",
                                           "ddf_sign_flip", "yes_no_reversed"] + [f"{c}_sign_flip" for c in CHARTS] + ["projections_sign_flip"], stab_rows)

    # ---- 5. thresholds: what margin / agreement makes "Yes" honest -----------
    thr_rows = []
    recs = [r for r in records if r["variant"] == "blended" and r["next"] is not None and r["now"]["margin"] is not None]
    for margin in (0.05, 0.075, 0.10, 0.15, 0.20):
        for min_agree in (0, 1, 2, 3):
            sub = [r for r in recs if r["now"]["ddf_sign"] == 1 and r["now"]["proj_sign"] == 1 and r["now"]["margin"] >= margin
                   and r["now"]["propose"]["agree"] >= min_agree]
            if not sub:
                continue
            still_win = np.mean([r["next"]["ddf_sign"] == 1 for r in sub])
            still_win_m = np.mean([r["next"]["ddf_sign"] == 1 and r["next"]["margin"] is not None and r["next"]["margin"] >= THIN_MARGIN for r in sub])
            lost = np.mean([r["next"]["ddf_sign"] == -1 for r in sub])
            thr_rows.append([round(margin, 3), min_agree, len(sub), round(len(sub) / len(recs), 4), round(float(still_win), 4),
                             round(float(still_win_m), 4), round(float(lost), 4)])
    write_csv(args.out / "thresholds.csv", ["ddf_margin_at_least", "charts_agree_at_least", "trades", "share_of_all",
                                            "next_week_still_win", "next_week_still_win_5pct", "next_week_lose"], thr_rows)

    # ---- 6. accept line calibration against the charts' own next week --------
    acc_rows = []
    recs = [r for r in records if r["variant"] == "blended" and r["next"] is not None]
    for answer in ("Likely", "Toss-up", "Unlikely"):
        for conf in ("High", "Medium", "Low"):
            sub = [r for r in recs if r["now"]["accept"]["answer"] == answer and r["now"]["accept"]["confidence"] == conf]
            if not sub:
                continue
            same = np.mean([r["next"]["accept"]["answer"] == answer for r in sub])
            ci = boot_ci([r["next"]["accept"]["answer"] == answer for r in sub], nrng, 500)
            acc_rows.append([answer, conf, len(sub), round(float(same), 4), round(ci[1], 4), round(ci[2], 4)])
    write_csv(args.out / "accept_stability.csv", ["accept", "confidence", "trades_with_next_week", "same_answer_next_week", "lo95", "hi95"], acc_rows)

    # ---- 7. superseded snapshots: same week, different pull -----------------
    sup_rows = []
    sup_dir = HISTORY / "superseded"
    for w in weeks:
        path = sup_dir / f"week-{w}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        served = hist.week_doc(w)["sources"]
        for src, versions in (doc.get("versions") or {}).items():
            if src not in CHARTS:
                continue
            seen = {served.get(src, {}).get("fingerprint")}
            for ver in versions:
                if not ver.get("complete") or ver.get("fingerprint") in seen:
                    continue
                seen.add(ver.get("fingerprint"))
                natives = {}
                for s2, entry in served.items():
                    if s2 in vr.SOURCES and entry.get("complete"):
                        natives[s2] = vr.snapshot_natives(inp, s2, ver if s2 == src else entry, SETTING["scoring"])
                res = vr.run_pipeline(base.league, base._sources(natives), base.pos_of, list(natives), None, lineup=base.lineup, hidden=set())
                alt = rows_from_result(res, inp)
                flips = []
                sign_flips = []
                for t in trades_by_week[w]:
                    g1, r1 = trade_rows(t, rows_by_week[w]); g2, r2 = trade_rows(t, alt)
                    if not g1 or not g2:
                        continue
                    e1 = evaluate(g1, r1, charts_by_week[w]); e2 = evaluate(g2, r2, charts_by_week[w])
                    flips.append(e1["propose"]["answer"] != e2["propose"]["answer"])
                    a, b = e1["chart_signs"].get(src), e2["chart_signs"].get(src)
                    if a not in (None, 0) and b not in (None, 0):
                        sign_flips.append(a != b)
                sup_rows.append([w, src, str((ver.get("_sort") or [ver.get("captured_at")])[0])[:16], len(flips), round(float(np.mean(flips)), 4) if flips else None,
                                 len(sign_flips), round(float(np.mean(sign_flips)), 4) if sign_flips else None])
    write_csv(args.out / "superseded_snapshots.csv", ["week", "chart", "other_pull_time", "trades", "propose_answer_differs",
                                                      "trades_chart_points", "chart_direction_differs"], sup_rows)

    # ---- port check ----------------------------------------------------------
    port = {"ran": False}
    if args.verify_port:
        w = weeks[-1]
        ev = [r["now"] for r in records if r["variant"] == "blended" and r["drawn"] == w]
        port = verify_port(rows_by_week[w], charts_by_week[w], trades_by_week[w], ev, args.port_trades)
        # and the live week with its holds (fewer charts), through Setting rows
        live_trades = sample_trades(live, 100, random.Random(SEED + 1))
        live_ev = []
        for t in live_trades:
            g, r = trade_rows(t, live)
            live_ev.append(evaluate(g, r, live_charts))
        port["live"] = verify_port(live, live_charts, live_trades, live_ev, 200)
    (args.out / "port_check.json").write_text(json.dumps(port, indent=1, default=str))

    # ---- summary -------------------------------------------------------------
    meta["trades_drawn"] = {w: len(t) for w, t in trades_by_week.items()}
    meta["records"] = len(records)
    meta["port_check"] = {k: v for k, v in port.items() if k != "examples"}
    (args.out / "run_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    write_summary(args.out, meta, records, weeks, charts_by_week, high_rows, stab_rows, thr_rows, acc_rows, corr_rows, dir_rows, sup_rows, label_rows, grp_rows)
    print(f"wrote {args.out}  trades={sum(meta['trades_drawn'].values())}  port_check={meta['port_check']}")
    return 0


def write_summary(out, meta, records, weeks, charts_by_week, high_rows, stab_rows, thr_rows, acc_rows, corr_rows, dir_rows, sup_rows, label_rows, grp_rows):
    L = []
    L.append(f"# Post 8 outputs ({meta['run_at'][:10]}, {meta['engine']})\n")
    L.append(f"Setting {meta['setting']}; weeks {weeks}; trades drawn per week {meta['trades_drawn']}; balance band {meta['balance_band']}; seed {meta['seed']}.\n")
    L.append(f"Live week {meta['live']['content_week']}: charts available on the page {meta['live']['charts_available']}; excluded {meta['live']['excluded']}.\n")
    L.append(f"Port check: {meta['port_check']}\n")
    blended = [r for r in records if r["variant"] == "blended"]
    n = len(blended)
    L.append("\n## Label frequencies, all weeks pooled (DDF Value = blended, the live rule)\n")
    for line in ("propose", "propose reason", "accept", "deal", "charts agree"):
        c = Counter()
        for r in blended:
            if line == "propose": c[f'{r["now"]["propose"]["answer"]} / {r["now"]["propose"]["confidence"]}'] += 1
            elif line == "propose reason": c[f'{r["now"]["propose"]["answer"]}: {r["now"]["propose"]["reason"]}'] += 1
            elif line == "accept": c[f'{r["now"]["accept"]["answer"]} / {r["now"]["accept"]["confidence"]}'] += 1
            elif line == "deal": c[str(r["now"]["deal"])] += 1
            else: c[f'{r["now"]["propose"]["agree"]} of {r["now"]["propose"]["of"]}'] += 1
        L.append(f"\n{line}:\n")
        L.append("| label | trades | share |\n|---|---|---|\n")
        for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
            L.append(f"| {k} | {v} | {pct(v / n)} |\n")
    finder = sum(1 for r in blended if r["now"]["finder"])
    L.append(f"\nFinder rule (DDF win and 3+ of 4 charts have the rival even or winning): {finder} of {n} ({pct(finder / n)}).\n")
    proj = [r for r in records if r["variant"] == "projections"]
    c = Counter(f'{r["now"]["propose"]["answer"]} / {r["now"]["propose"]["confidence"]}' for r in proj)
    L.append("\nPropose line if DDF Value were projections only (PR #814):\n\n| label | trades | share |\n|---|---|---|\n")
    for k, v in sorted(c.items(), key=lambda kv: -kv[1]):
        L.append(f"| {k} | {v} | {pct(v / len(proj))} |\n")
    L.append("\n## Propose answer by chart-agreement count (blended)\n\n| charts agree | Yes | No | Unclear | trades |\n|---|---|---|---|---|\n")
    byagree = defaultdict(Counter)
    for r in blended:
        byagree[r["now"]["propose"]["agree"]][r["now"]["propose"]["answer"]] += 1
    for k in sorted(byagree):
        c = byagree[k]; tot = sum(c.values())
        L.append(f"| {k} | {pct(c['Yes'] / tot)} | {pct(c['No'] / tot)} | {pct(c['Unclear'] / tot)} | {tot} |\n")
    L.append("\n## Next-week flips by label (see high_by_agree.csv, stability.csv)\n")
    L.append("\n| variant | propose | confidence | charts agree | trades | propose answer changes | 95% CI | DDF sign flips | Yes<->No |\n|---|---|---|---|---|---|---|---|---|\n")
    for row in high_rows:
        L.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {pct(row[5])} | {pct(row[6])} to {pct(row[7])} | {pct(row[8])} | {pct(row[11])} |\n")
    L.append("\n## High-confidence labels by package size, tier and position (blended)\n\n| propose | group | trades | answer changes next week | 95% CI | DDF sign flips | all charts agreed |\n|---|---|---|---|---|---|---|\n")
    for row in grp_rows:
        L.append(f"| {row[0]} / High | {row[2]} | {row[3]} | {pct(row[4])} | {pct(row[5])} to {pct(row[6])} | {pct(row[7])} | {pct(row[8])} |\n")
    L.append("\n## Stability week to week\n\n| variant | weeks | trades | propose | accept | deal | DDF sign | Yes<->No | " + " | ".join(CHARTS) + " | projections |\n|---|---|---|---|---|---|---|---|" + "---|" * (len(CHARTS) + 1) + "\n")
    for row in stab_rows:
        L.append(f"| {row[0]} | {row[1]}->{row[2]} | {row[3]} | " + " | ".join("" if v is None else pct(v) for v in row[4:]) + " |\n")
    L.append("\n## Thresholds (DDF Value and DDF Projections both win now; blended)\n\n| DDF margin >= | charts agree >= | trades | share of all | still win next week | still win by 5%+ | lose next week |\n|---|---|---|---|---|---|---|\n")
    for row in thr_rows:
        L.append(f"| {pct(row[0], 1)} | {row[1]} | {row[2]} | {pct(row[3])} | {pct(row[4])} | {pct(row[5])} | {pct(row[6])} |\n")
    L.append("\n## Will they accept: same answer next week\n\n| answer | confidence | trades | same next week | 95% CI |\n|---|---|---|---|---|\n")
    for row in acc_rows:
        L.append(f"| {row[0]} | {row[1]} | {row[2]} | {pct(row[3])} | {pct(row[4])} to {pct(row[5])} |\n")
    L.append("\n## Pairwise rank correlation (Spearman), latest saved week\n\n| chart a | chart b | group | players | rho |\n|---|---|---|---|---|\n")
    w = weeks[-1]
    for row in corr_rows:
        if row[0] == w:
            L.append(f"| {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |\n")
    L.append("\n## Pairwise trade-direction agreement (share of trades both series point the same way)\n\n| a | b | group | trades | same direction |\n|---|---|---|---|---|\n")
    for row in dir_rows:
        L.append(f"| {row[0]} | {row[1]} | {row[3]} | {row[4]} | {pct(row[5])} |\n")
    L.append("\n## Superseded snapshots (same week, a different pull of one chart)\n\n| week | chart | other pull | trades | propose answer differs | chart direction differs |\n|---|---|---|---|---|---|\n")
    for row in sup_rows:
        L.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {'' if row[4] is None else pct(row[4])} | {'' if row[6] is None else pct(row[6])} |\n")
    (out / "summary.md").write_text("".join(L))


if __name__ == "__main__":
    raise SystemExit(main())
