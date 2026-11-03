#!/usr/bin/env python3
"""Write the worked example in docs/methodology.md from the fixture (JEG-1397).

The section "Worked example (tests/fixtures/value_pipeline_worked_example.json)"
quotes reference numbers that drifted from the code twice (J1393-04: the old
D'Hondt bench, the first-non-starter starter line and the old fill sets). This
script runs the fixture through the clean-room spec reference
(pipelines/spec_reference) and writes every number of that section between the
BEGIN/END markers below: the legacy slices mode (the fixture's `expected`
block, no lineup parameters), its hand-check, and the current expected-starts
mode (`variant_expected_starts`). The engine and the Python reference
reproduce the same fixture to 1e-6 (tests/test_value_pipeline_engine.py,
tests/test_value_reference_worked_example.py), so the doc quotes all three.

No value math lives here: every number is read from the spec reference's
result; the only arithmetic is the display of a ratio or a product the result
already holds. tests/test_methodology_worked_example.py fails when the doc and
this output differ.

Usage: python3 tools/methodology_worked_example.py [--check] [--print]
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))
from spec_reference import value_pipeline as vp  # noqa: E402
from spec_reference import worked_example as we  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"
DOC = REPO / "docs" / "methodology.md"
BEGIN = ("<!-- BEGIN generated worked example: python3 tools/methodology_worked_example.py "
         "(JEG-1397). Do not edit by hand. -->")
END = "<!-- END generated worked example -->"

POS = vp.POSITIONS


def f(x, nd: int = 6) -> str:
    """A number as the doc shows it: up to `nd` decimals, no trailing zeros."""
    if x is None:
        return "null"
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, int):
        return str(x)
    s = f"{float(x):.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


class Ctx:
    def __init__(self, fx: dict):
        self.fx = fx
        self.inp = we.fixture_inputs(fx)
        self.name = {int(k): v["name"] for k, v in fx["players"].items()}
        self.pos = {int(k): v["pos"] for k, v in fx["players"].items()}
        self.inputs = fx["inputs"]
        self.included = [s for s, v in self.inputs.items() if v["status"] == "included"]
        self.held = [s for s, v in self.inputs.items() if v["status"] != "included"]
        self.charts = [s for s, v in self.inputs.items() if v["family"] == "chart"]
        self.projs = [s for s, v in self.inputs.items() if v["family"] == "projection"]

    def values(self, s: str) -> dict:
        return {int(k): float(v) for k, v in self.inputs[s]["values"].items()}

    def nm(self, k) -> str:
        return self.name[int(k)]

    def run(self, change: dict | None = None, lineup: dict | None = None) -> dict:
        if lineup is None:
            return we.run_fixture(self.fx, change)
        s = copy.deepcopy(self.fx["setting"])
        s.update(change or {})
        return vp.run_week(vp.Setting.from_fixture(s), self.inp["pos_of"], self.inp["sources"],
                           self.inp["included"], names=self.inp["names"], lineup=lineup)


def _setting_line(s: dict) -> str:
    slots = " ".join(f"{p}{n}" for p, n in s["slots"].items())
    sf = "no superflex" if not s.get("superflex") else f"superflex {s['superflex']}"
    return (f"{s['teams']} teams, {slots} FLEX{s['flex']} ({'/'.join(s['flex_eligible'])}), {sf}, "
            f"bench {s['bench_per_team']} per team")


def _alloc_table(alloc: dict) -> list:
    out = ["| Position | Dedicated | Superflex | Flex | Bench | Starters `S_p` | Rostered `N_p` |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    for p in POS:
        a = alloc[p]
        out.append(f"| {p} | {a['dedicated']} | {a['superflex']} | {a['flex']} | {a['bench']} | "
                   f"{a['starters']} | {a['rostered']} |")
    return out


def _bench_seat_order(c: Ctx, setting_change: dict | None) -> list:
    """Who takes each bench seat, in order, with the score that won it.

    The order is read from the convention itself: the counts after 1, 2, ...
    seats of the same greedy fill (VP-2.2d), differenced. The score shown is
    VP-2.2d's `max(0, m) x c_p^(1 + floor(k / t1_p))`; the generator stops if
    the seat it shows did not have the highest score, so the doc cannot quote
    a score the convention did not use."""
    from lib import roster_convention as rc
    s = copy.deepcopy(c.fx["setting"])
    s.update(setting_change or {})
    st = vp.Setting.from_fixture(s)
    res = c.run(setting_change)
    alloc = res["allocation"]
    m = res["mean_ppg"]
    order = vp.score_order(m, c.pos)
    T = st.teams
    starters = {p: alloc[p]["starters"] for p in POS}
    remaining = {p: order.get(p, [])[starters[p]:] for p in POS}
    slots = {p: int(st.slots.get(p, 0)) for p in POS}
    two_qb = st.superflex > 0 or slots.get("QB", 1) >= 2
    cov = {p: starters[p] / T * (rc._BYE_RATE + rc._BENCH_MISS_RATE.get(p, 0.12)) for p in POS}
    t1 = {p: max(1, round(2.0 * cov[p] * T)) for p in POS}

    def score(p, k):
        return max(0.0, float(m[remaining[p][k]])) * cov[p] ** (1 + k // t1[p])

    seats, prev = [], {p: 0 for p in POS}
    for n in range(1, T * st.bench_per_team + 1):
        got = rc.vorp_bench_allocate(starters, remaining, m, T, n, slots, two_qb, None)
        won = [p for p in POS if got[p] > prev[p]]
        if not won:
            break
        p = won[0]
        live = {q: score(q, prev[q]) for q in POS if prev[q] < len(remaining[q])}
        if abs(live[p] - max(live.values())) > 1e-12:
            raise SystemExit(f"bench seat {n}: shown score for {p} is not the highest; VP-2.2d text is stale")
        seats.append((p, remaining[p][prev[p]], live[p]))
        prev = got
    return seats, cov, t1


def _bench_text(c: Ctx, res: dict, change: dict | None) -> list:
    seats, cov, t1 = _bench_seat_order(c, change)
    m = res["mean_ppg"]
    return ["- Bench (VP-2.2d): " + str(len(seats)) + " seats, one at a time, each to the highest "
            "`max(0, m) x c_p^(1 + floor(k / t1_p))`, with `c_p` "
            + ", ".join(f"{p} {f(cov[p])}" for p in POS) + " and `t1_p` "
            + ", ".join(f"{p} {t1[p]}" for p in POS) + ". In order: "
            + ", ".join(f"{c.nm(k)} (m {f(m[k])}, score {f(sc)})" for p, k, sc in seats) + "."]


def _fill_in_rows(c: Ctx, res: dict) -> list:
    rows = []
    for ch in c.charts:
        for p in POS:
            info = res["sources"][ch]["positions"][p]
            for k, e in sorted((info.get("imputation_ratios") or {}).items(),
                               key=lambda kv: (-res["mean_ppg"].get(int(kv[0]), 0), int(kv[0]))):
                k = int(k)
                if e["path"] == "peers":
                    used = [(pk, pv) for pk, pv in e["peers"].items() if pv.get("usable")]
                    path = f"peers {', '.join(pk for pk, _ in used)} (median of {len(used)})"
                    detail = "; ".join(
                        f"{pk} {f(pv['num'])} / {f(pv['den'])} on {len(pv['fit_players'])} shared x "
                        f"{f(pv['peer_native'])} = {f(pv['estimate'])}" for pk, pv in used)
                else:
                    cu = e["curve"]
                    path = f"curve on {len(cu['points'])} listed {p}s"
                    detail = (f"`native = {f(cu['intercept'])} + {f(cu['slope'])} x m`, "
                              f"m = {f(cu['mean_ppg'])}")
                shown = f(e["value"])
                if e["capped"]:
                    shown += f" (capped at {ch}'s lowest listed {p})"
                elif info["method"] == "estimated" and abs(info["waiver_value"] - e["value"]) < 1e-12:
                    shown += f" (sets {ch}'s {p} waiver line)"
                rows.append(f"| {ch} | {c.nm(k)} | {path} | {detail} | {f(e['raw'])} | {shown} |")
    return rows


def _below_depth(c: Ctx, res: dict) -> list:
    """Players in the fill set's position a chart neither lists nor estimates,
    at a position it prices: 0 on that chart in every view (VP-2.4 i)."""
    out = []
    for ch in c.charts:
        listed = c.values(ch)
        for p in POS:
            info = res["sources"][ch]["positions"][p]
            if info["method"] == "no_players":
                continue
            est = {int(k) for k in (info.get("imputation_ratios") or {})}
            miss = [k for k in sorted(c.pos, key=lambda k: (-res["mean_ppg"].get(k, 0), k))
                    if c.pos[k] == p and k not in listed and k not in est]
            if miss:
                out.append(f"`{ch}` {p}: {', '.join(c.nm(k) for k in miss)}")
    return out


def _weights_lines(res: dict) -> list:
    smm, bmm, W = res["starter_mix_mean"], res["bench_mix_mean"], res["ddf_weights"]
    bench_total = math.fsum(W[f"{p}|bench"] for p in POS)
    return [
        f"Starter mix mean {', '.join(f'{p} {f(smm[p])}' for p in POS)}; bench mix mean "
        f"{', '.join(f'{p} {f(bmm[p])}' for p in POS)}. So `W` = "
        + ", ".join(f"{p} starter {f(W[f'{p}|starter'])}, {p} bench {f(W[f'{p}|bench'])}" for p in POS)
        + f" (the bench groups sum to {f(bench_total)}; bench share applied {f(res['bench_share_applied'])}).",
    ]


def _work(c: Ctx, res: dict, s: str, p: str) -> list:
    pl = res["sources"][s]["players"]
    keys = [k for k, v in pl.items() if v["pos"] == p]
    return sorted(keys, key=lambda k: (-pl[k]["native"], pl[k]["imputed"], k))


def _lines_text(c: Ctx, res: dict, s: str, p: str, k: int) -> tuple[str, dict]:
    """The starter line and waiver line of source `s` at `p`, spelled out."""
    info = res["sources"][s]["positions"][p]
    work = _work(c, res, s, p)
    pl = res["sources"][s]["players"]
    S, N = info["starters"], info["rostered"]
    vals = [pl[w]["native"] for w in work]
    last, first = work[S - 1], work[S]
    lo, hi = max(0, N - 3), min(len(work), N + 3 + 1)
    band = ", ".join(f(v) for v in vals[lo:hi])
    txt = (f"`S_{p}` = {S}, `N_{p}` = {N}. Starter line {f(info['starter_line'])} = the midpoint of "
           f"{c.nm(last)} ({f(pl[last]['native'])}, index {S - 1}, the last starter) and "
           f"{c.nm(first)} ({f(pl[first]['native'])}, index {S}, the first non-starter) (VP-2.5). "
           f"Waiver line {f(info['waiver_value'])} = the mean of the {hi - lo} values at indexes "
           f"{lo} to {hi - 1} ({band}), the projection band of VP-2.3.")
    return txt, info


def _ddf_text(c: Ctx, row: dict) -> str:
    b, pj = row["ddf_blended"], row["ddf_projections"]
    ch = ", ".join(f"{s} {f(row['adjusted'][s])}" for s in b["sources"])
    pr = ", ".join(f"{s} {f(row['adjusted'][s])}" for s in pj["sources"])
    held = [s for s in c.held if row["adjusted"].get(s) is not None]
    held_txt = "".join(f" `{s}` is held: shown ({f(row['adjusted'][s])} Adjusted), never counted."
                       for s in held)
    return (f"Its **DDF Value** is **{f(b['value'])}**: the equal-weight mean of the Adjusted values "
            f"of the {b['count']} included charts ({ch}; VP-6.3). Its DDF Value (projections) is "
            f"{f(pj['value'])}, the mean over the {pj['count']} included projections ({pr}).{held_txt}")


def legacy(c: Ctx) -> list:
    fx, res = c.fx, c.run()
    s = fx["setting"]
    alloc = res["allocation"]
    m = res["mean_ppg"]
    out = []
    starting = res["starting_slots_per_team"]
    out += [f"**Legacy slices mode** (no lineup parameters: the fixture's `expected` block). "
            "This is the VP-2.6 rule that ES-5 replaced on the live site; the fixture keeps it as the "
            "clean-room check of VP-2 to VP-7.", ""]
    out += [f"**Setting.** {_setting_line(s)}, bench share {f(s['bench_share'])}. Pie = "
            f"{f(vp.PIE_PER_STARTING_SLOT)} x {s['teams']} x {starting} = **{f(res['pie'])}**.", ""]
    projs = [x for x in c.projs if x in c.included]
    charts = [x for x in c.charts if x in c.included]
    srcs = (f"**Sources.** Projections {', '.join(f'`{x}`' for x in projs)} and charts "
            f"{', '.join(f'`{x}`' for x in charts)} are included.")
    for h in c.held:
        hv, base = c.values(h), None
        for other in charts:
            ov = c.values(other)
            if set(ov) == set(hv) and ov:
                r = {round(hv[k] / ov[k], 12) for k in ov if ov[k]}
                if len(r) == 1:
                    base = (other, r.pop())
                    break
        srcs += f" `{h}` is {c.inputs[h]['status']}"
        srcs += (f"; its natives are exactly {f(base[1])} x `{base[0]}`." if base else ".")
    unlisted = [k for k in sorted(c.pos) if not any(k in c.values(ch) for ch in c.charts)]
    for k in unlisted:
        by = [x for x in projs if k in c.values(x)]
        srcs += (f" {c.nm(k)} is listed by no chart and projected only by "
                 f"{', '.join(f'`{x}` ({f(c.values(x)[k])})' for x in by)}.")
    out += [srcs, ""]

    out += ["**League allocation (by projected points, VP-2.2).**", ""]
    out += _alloc_table(alloc)
    out += [""] + _bench_text(c, res, None)
    order = vp.score_order(m, c.pos)
    ded = {p: alloc[p]["dedicated"] + alloc[p]["superflex"] for p in POS}
    cands = sorted([k for p in s["flex_eligible"] for k in order.get(p, [])[ded[p]:]],
                   key=lambda k: (-m[k], vp.POS_ORDER[c.pos[k]], k))
    winners = cands[:s["teams"] * s["flex"]]
    fc = res["flex_contrast"]
    c1 = charts[0]
    own = fc[f"{c1}_by_own_values_superseded"]
    out += ["- Flex candidates by `m`: " + ", ".join(f"{c.nm(k)} {f(m[k])}" for k in cands[:len(winners) + 1])
            + f". The {len(winners)} flex slots go to "
            + " and ".join(f"**{c.pos[k]}**" for k in winners)
            + f". By `{c1}`'s own values (the superseded rule, `expected.flex_contrast`) they would go to "
            + " and ".join(f"{own[p]} {p}" for p in POS if own[p]) + "."]
    out += ["- Fill sets (first `N_p + 1` by `m`): "
            + "; ".join(", ".join(c.nm(k) for k in res["fill_sets"][p]) for p in POS) + ".", ""]

    out += ["**Fill-in estimates (VP-2.4).**", "",
            "| Chart | Player | Path | Detail | Raw | Shown |", "| --- | --- | --- | --- | --- | --- |"]
    out += _fill_in_rows(c, res)
    out += ["", "Below rosterable depth (a priced position, neither listed nor estimated, so 0 on that "
            "chart in every view): " + "; ".join(_below_depth(c, res)) + ".", ""]

    out += [f"**DDF weights (bench share {f(s['bench_share'])}, VP-4).** " + _weights_lines(res)[0], ""]

    # Hand-check: the top RB of the first projection.
    src, p = projs[0], "RB"
    k = _work(c, res, src, p)[0]
    pl = res["sources"][src]["players"][k]
    lines, info = _lines_text(c, res, src, p, k)
    G, R, W = res["sources"][src]["groups"], res["sources"][src]["rates"], res["ddf_weights"]
    gb, gs = f"{p}|bench", f"{p}|starter"
    out += [f"**Hand-check one value (legacy slices).** `{src}`, {c.nm(k)}: native {f(pl['native'])}. "
            + lines
            + f" Bench slice `min({f(pl['native'])}, {f(info['starter_line'])}) - {f(info['waiver_value'])}` = "
            f"{f(pl['bench_slice'])}, starter slice `{f(pl['native'])} - {f(info['starter_line'])}` = "
            f"{f(pl['starter_slice'])} (VP-2.6). `{src}`'s {p} groups are {f(G[gb])} bench and {f(G[gs])} "
            f"starter, so the rates are `{f(res['pie'])} x {f(W[gb])} / {f(G[gb])} = {f(R[gb])}` and "
            f"`{f(res['pie'])} x {f(W[gs])} / {f(G[gs])} = {f(R[gs])}`, and "
            f"`A = {f(pl['bench_slice'])} x {f(R[gb])} + {f(pl['starter_slice'])} x {f(R[gs])}` = "
            f"**{f(pl['adjusted'])}** (VP-5). " + _ddf_text(c, res["rows"][k]), ""]

    # What else it pins.
    rows = res["rows"]
    out += ["**What else it pins.**", "", "| Case | Player | Result |", "| --- | --- | --- |"]
    for u in unlisted:
        r = rows[u]
        est = r["estimated"]
        priced = [x for x in projs if r["adjusted"].get(x) is not None]
        miss = [x for x in projs if r["adjusted"].get(x) is None]
        low = r["ddf_projections"]
        pu = c.pos[u]
        est_pairs = []
        for x in est:
            info = res["sources"][x]["positions"][pu]
            est_pairs.append((x, info["imputation_ratios"][u]["value"], info["waiver_value"]))
        below = all(v <= w + 1e-12 for _, v, w in est_pairs)
        adj = [r["adjusted"][x] for x in r["ddf_blended"]["sources"]]
        adj_txt = (f"each of the {len(adj)} Adjusted values is {f(adj[0])}" if len(set(adj)) == 1
                   else "Adjusted " + ", ".join(f(a) for a in adj))
        why = (f"every estimate is at or below its chart's {pu} waiver line ("
               + ", ".join(f"{x} {f(v)} against {f(w)}" for x, v, w in est_pairs) + "), so ") if below else ""
        out.append(
            f"| Estimated value counts in DDF | {c.nm(u)} | estimated on {', '.join(est)}; "
            f"DDF Value {f(r['ddf_blended']['value'])} over {r['ddf_blended']['count']} charts: "
            + why + adj_txt
            + f"; DDF Value (projections) {f(low['value'])} from {', '.join(priced)}"
            + (", low confidence (" + ", ".join(f"`{x}` is null" for x in miss) + ")" if low.get("low_confidence") else "")
            + " |")
    capped = [(ch, int(k), e) for ch in c.charts for p in POS
              for k, e in (res["sources"][ch]["positions"][p].get("imputation_ratios") or {}).items()
              if e["capped"] and e["path"] == "peers"]
    for ch, k, e in capped:
        out.append(f"| Capped ratio estimate | {c.nm(k)} on {ch} | estimated {f(e['value'])}, Adjusted "
                   f"{f(rows[k]['adjusted'][ch])}; DDF Value {f(rows[k]['ddf_blended']['value'])} |")
    idx_chart = charts[-1]
    ix = res["indexed"][idx_chart]
    est_here = [int(kk) for p in POS for kk in (res["sources"][idx_chart]["positions"][p].get("imputation_ratios") or {})]
    shown = "; ".join(f"{c.nm(kk)}'s estimate shows {f(rows[kk]['indexed'][idx_chart])} Indexed"
                      for kk in est_here if c.pos[kk] == "RB")
    out.append(f"| Indexed basis excludes estimates | {idx_chart} | `f = {f(ix['ddf_total'])} / "
               f"{f(ix['native_total'])} = {f(ix['factor'])}` over its {ix['shared_players']} listed players"
               + (f"; {shown}" if shown else "") + " |")
    for h in c.held:
        base = None
        for other in charts:
            if all(abs((rows[kk]["adjusted"].get(h) or 0) - (rows[kk]["adjusted"].get(other) or 0)) < 1e-9
                   and abs((rows[kk]["indexed"].get(h) or 0) - (rows[kk]["indexed"].get(other) or 0)) < 1e-9
                   for kk in rows):
                base = other
                break
        out.append(f"| Held source shown, never counts | {h} | "
                   + (f"Adjusted and Indexed identical to {base}'s on every row (to 1e-9)" if base
                      else "Adjusted and Indexed differ from every included chart")
                   + "; in no DDF Value |")
    rb_rank = [kk for kk in res["default_ranking"] if c.pos[kk] == "RB"]
    tier_bits = [f"{c.nm(kk)} (DDF Value {f(rows[kk]['ddf_blended']['value'])}) is "
                 f"in the {rows[kk]['ddf_tier']} tier by the flex" for kk in winners if c.pos[kk] == "TE"]
    tier_bits += [f"{c.nm(u)} (rank {rb_rank.index(u) + 1} of RB) is in the {rows[u]['ddf_tier']} tier" for u in unlisted]
    out.append("| Tiers | slot fill = the allocation | " + "; ".join(tier_bits) + " |")
    var = fx.get("variant_bench_share_0_10")
    if var:
        vr = c.run(var["setting_change"])
        vb = math.fsum(vr["ddf_weights"][f"{p}|bench"] for p in POS)
        out.append(f"| Bench share slider {f(var['setting_change']['bench_share'])} | "
                   f"`variant_bench_share_0_10` | bench groups sum to {f(vb)}; {c.nm(k)}'s DDF Value "
                   f"{f(vr['rows'][k]['ddf_blended']['value'])} |")
    return out


def current(c: Ctx) -> list:
    fx = c.fx
    var = fx.get("variant_expected_starts")
    if not var:
        return ["The fixture carries no expected-starts variant."]
    lineup, change = var["lineup"], var["setting_change"]
    res = c.run(change, lineup)
    s = {**fx["setting"], **change}
    alloc = res["allocation"]
    m = res["mean_ppg"]
    out = ["**Current rule: expected starts (ES-0 to ES-15; the fixture's `variant_expected_starts`).** "
           f"Same players and sources; bench {s['bench_per_team']} per team, so that WR gets a second depth band. "
           "Lineup parameters are round illustrative numbers for a hand-sized league, not the measured "
           "`config/lineup_parameters.json`: bye "
           f"{f(lineup['bye'])}, projection confidence {f(lineup['projection_confidence'])}, and "
           + "; ".join(f"{p} `m` {f(v['m'])}, `sigma` {f(v['sigma_rel'])}, floor {f(v['sigma_floor'])}"
                       for p, v in lineup["positions"].items())
           + ". The bench share is computed (no override).", ""]
    out += _alloc_table(alloc)
    out += [""] + _bench_text(c, res, change)
    cs = res["chart_sigma"]
    out += ["- Chart `sigma` (ES-6, before the projection-confidence scale): "
            + ", ".join(f"{p} {f(cs[p]['sigma_rel'])}" for p in POS) + ".", ""]

    src, p = [x for x in c.projs if x in c.included][0], "RB"
    k = _work(c, res, src, p)[0]
    pl = res["sources"][src]["players"][k]
    lines, info = _lines_text(c, res, src, p, k)
    prm = lineup["positions"][p]
    T = s["teams"]
    q = lineup["bye"] + (1 - lineup["bye"]) * prm["m"]
    sd = max(prm["sigma_rel"] * pl["native"], prm["sigma_floor"])
    v = pl["vorp"]
    bands = "; ".join(f"depth {b['depth']} `({f(b['lo'])}, {f(b['hi'])}]` fill {f(b['fill'])}" for b in info["bands"])
    fill_prob = pl["bench_slice"] / (info["avail"] * v) if v else 0.0
    G, R, W = res["sources"][src]["groups"], res["sources"][src]["rates"], res["ddf_weights"]
    gb, gs = f"{p}|bench", f"{p}|starter"
    out += [f"**Hand-check one value (expected starts).** `{src}`, {c.nm(k)}: native {f(pl['native'])}. "
            + lines
            + f" Value above waivers `v` = {f(v)}. `avail = (1 - {f(lineup['bye'])}) x (1 - {f(prm['m'])})` = "
            f"{f(info['avail'])}; `n_{p}` = {info['lineup']['n_per_team']} starter per team "
            f"(`S_{p} / T` = {info['starters']} / {T}), out-probability `q` = {f(q)}; bands: {bands} (ES-3, ES-4). "
            f"`s(x) = max({f(prm['sigma_rel'])} x {f(pl['native'])}, {f(prm['sigma_floor'])})` = {f(sd)}, so "
            f"`P(X > {f(info['starter_line'])})` = {f(pl['start_worthy'])}. Start-worthy part "
            f"`{f(info['avail'])} x {f(v)} x {f(pl['start_worthy'])}` = {f(pl['starter_slice'])}; fill-in part "
            f"`{f(info['avail'])} x {f(v)} x {f(fill_prob)}` = {f(pl['bench_slice'])} (ES-5; the last factor is "
            f"`sum_k fill_k x P(band k)`). Lineup share {f(pl['lineup_share'])}. The rates are "
            f"`{f(res['pie'])} x {f(W[gb])} / {f(G[gb])} = {f(R[gb])}` and "
            f"`{f(res['pie'])} x {f(W[gs])} / {f(G[gs])} = {f(R[gs])}`, so "
            f"`A = {f(pl['bench_slice'])} x {f(R[gb])} + {f(pl['starter_slice'])} x {f(R[gs])}` = "
            f"**{f(pl['adjusted'])}**. " + _ddf_text(c, res["rows"][k]), ""]
    rd = res["bench_share_readout"]
    out += [f"**Bench share, computed.** The bench groups' DDF weights sum to {f(res['bench_share_applied'])} "
            "(the pie paid on fill-in parts, ES-5); the readout by position is "
            + ", ".join(f"{p} {f(rd[p])}" for p in POS) + f", overall {f(rd['overall'])}."]
    ov = fx.get("variant_expected_starts_override")
    if ov:
        o = ov["setting_change"]["bench_share_override"]
        orr = c.run(ov["setting_change"], ov["lineup"])
        out[-1] += (f" With the reader's override at {f(o)} (`variant_expected_starts_override`) the bench "
                    f"groups sum to {f(orr['bench_share_applied'])} and {c.nm(k)}'s DDF Value is "
                    f"{f(orr['rows'][k]['ddf_blended']['value'])}.")
    return out


def render(fx: dict | None = None) -> str:
    fx = fx or json.loads(FIXTURE.read_text(encoding="utf-8"))
    c = Ctx(fx)
    body = legacy(c) + [""] + current(c)
    return "\n".join([BEGIN, ""] + body + ["", END])


def _span(doc: str) -> tuple[int, int]:
    """Return (start, end) of the one generated block; exit on missing, duplicate or misordered markers."""
    nb, ne = doc.count(BEGIN), doc.count(END)
    a, b = doc.find(BEGIN), doc.find(END)
    if nb != 1 or ne != 1 or b < a:
        raise SystemExit(f"{DOC.relative_to(REPO)}: expected exactly one BEGIN and one END "
                         f"generated worked-example marker, found {nb} and {ne}")
    return a, b + len(END)


def splice(doc: str, block: str) -> str:
    a, b = _span(doc)
    return doc[:a] + block + doc[b:]


def current_block(doc: str) -> str:
    a, b = _span(doc)
    return doc[a:b]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if docs/methodology.md differs")
    ap.add_argument("--print", action="store_true", help="print the block, write nothing")
    args = ap.parse_args(argv)
    block = render()
    if args.print:
        print(block)
        return 0
    doc = DOC.read_text(encoding="utf-8")
    if args.check:
        same = current_block(doc) == block
        print("methodology worked example:", "up to date" if same else
              "DIFFERS (run python3 tools/methodology_worked_example.py)")
        return 0 if same else 1
    DOC.write_text(splice(doc, block), encoding="utf-8")
    print(f"wrote the worked example to {DOC.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
