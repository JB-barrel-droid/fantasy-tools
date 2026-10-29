"""JEG-1047 research: how much one fringe player's projection moves a position.

Candidate waiver-line rules are swapped in through the reference's single
hook, `value_reference._waiver_value`, for the duration of a run; nothing is
written back. Rule "current" is the one-player rule used before JEG-1047, so
the comparison reads the same before and after the fix landed.

Mechanism under test: before JEG-1047 the projection legs (ESPN, CBS ROS,
Razzball) read each position's waiver line from a single player, the first one
past the league's rostered count. Every player's value above waivers is
`x - w`, so a change to that one player's projection moved every value at the
position. Jeremy chose the 7-player average band (2026-10-29), which is now
the engine's rule.

For each scoring x team count (the 12-combo grid), projection source and
position the script:

1. perturbs the waiver-line player's per-game projection by -1, -0.5, +0.5
   and +1 PPG (and, as a control, the top player at the position by -1 and
   +1), recomputes the setting, and measures how far every OTHER player at
   that position moves in that source's Adjusted value and in DDF
   Projections;
2. repeats that under each candidate line rule (hypothetical);
3. separately, reads the line each rule gives on every saved week (history
   snapshots), to show how much each rule moves week to week on real data.

Run: python3 tools/research/jeg1047_waiver_anchor.py
Writes the readout to docs/research/data/jeg1047_waiver_anchor.md and the full
case list to output/jeg1047_waiver_anchor.json (gitignored).
"""
from __future__ import annotations

import argparse
import copy
import inspect
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

import value_reference as vr  # noqa: E402

OUT_JSON = REPO / "output" / "jeg1047_waiver_anchor.json"   # full case list, 2.6 MB, not committed
OUT_MD = REPO / "docs" / "research" / "data" / "jeg1047_waiver_anchor.md"
HISTORY_DIR = REPO / "data" / "history"

SCORINGS = ("standard", "half_ppr", "ppr")
TEAMS = (8, 10, 12, 14)
PROJ = ("espn", "cbsros", "razzball")
DELTAS = (-1.0, -0.5, 0.5, 1.0)
STAR_DELTAS = (-1.0, 1.0)
MOVE_EPS = 0.05          # a value change smaller than this rounds away on the page
SRC_LABEL = {"espn": "ESPN", "cbsros": "CBS ROS", "razzball": "Razzball"}


# ---------------------------------------------------------------------------
# Candidate line rules (hypothetical). Each takes the position's work list
# values (sorted best first) and the rostered count n, and returns a line.
# ---------------------------------------------------------------------------
def _window(vals, n, k):
    lo, hi = max(0, n - k), min(len(vals), n + k + 1)
    return vals[lo:hi]


def rule_current(vals, n):
    return vals[n]


def rule_avg_band(k):
    return lambda vals, n: statistics.fmean(_window(vals, n, k))


def rule_median_band(k):
    return lambda vals, n: statistics.median(_window(vals, n, k))


def rule_local_quadratic(k):
    """Least-squares quadratic in rank over n-k..n+k, read at rank n
    (a Savitzky-Golay smoother; the fitted-curve option)."""
    def f(vals, n):
        lo, hi = max(0, n - k), min(len(vals), n + k + 1)
        xs = list(range(lo, hi))
        ys = vals[lo:hi]
        if len(xs) < 3:
            return statistics.fmean(ys)
        # Solve the 3x3 normal equations for y = a + b t + c t^2, t = x - n.
        ts = [x - n for x in xs]
        s = [sum(t ** p for t in ts) for p in range(5)]
        r = [sum(y * t ** p for t, y in zip(ts, ys)) for p in range(3)]
        m = [[s[0], s[1], s[2]], [s[1], s[2], s[3]], [s[2], s[3], s[4]]]

        def det(a):
            return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1])
                    - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                    + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
        d = det(m)
        if abs(d) < 1e-12:
            return statistics.fmean(ys)
        m0 = [[r[0], m[0][1], m[0][2]], [r[1], m[1][1], m[1][2]], [r[2], m[2][1], m[2][2]]]
        return det(m0) / d   # a = fitted value at t = 0
    return f


RULES = {
    "current": rule_current,
    "avg_band_3": rule_avg_band(3),
    "median_band_3": rule_median_band(3),
    "curve_5": rule_local_quadratic(5),
}
RULE_LABEL = {
    "current": "One player (rule before JEG-1047)",
    "avg_band_3": "Average band (7 players)",
    "median_band_3": "Median band (7 players)",
    "curve_5": "Fitted curve (11 players)",
    "time_2wk": "Time smoothing (this week and last, one player each)",
    "avg_band_3_time": "Average band + time smoothing",
}


# ---------------------------------------------------------------------------
# Swap the line rule in through the reference's single waiver hook.
# ---------------------------------------------------------------------------
_ORIG_WAIVER_VALUE = vr._waiver_value


def _install_patch():
    vr._waiver_value = _line_hook


_STATE = {"rule": "current", "prior": None}


def _line_hook(src, pos, vals, n):
    if src.family != "projection":
        return vals[n]
    rule = _STATE["rule"]
    base = "avg_band_3" if rule == "avg_band_3_time" else ("current" if rule == "time_2wk" else rule)
    line = RULES[base](vals, n)
    if rule in ("time_2wk", "avg_band_3_time"):
        prior = (_STATE["prior"] or {}).get((src.key, pos, base))
        if prior is not None:
            line = 0.5 * line + 0.5 * prior
    return line


# ---------------------------------------------------------------------------
# Running one setting.
# ---------------------------------------------------------------------------
def run(inp, scoring, teams):
    s = vr.Setting(inp, scoring, teams)
    res = s.result()
    return s, res


def lines_of(res, src):
    return {p: (res["sources"][src]["positions"].get(p) or {}) for p in vr.POSITIONS}


def snapshot(res, src):
    out = {}
    for i, r in res["rows"].items():
        out[i] = {
            "pos": r["pos"],
            "src": (r.get("adjusted") or {}).get(src),
            "proj": ((r.get("ddf") or {}).get("projections") or {}).get("value"),
            "blend": ((r.get("ddf") or {}).get("blended") or {}).get("value"),
        }
    return out


def diff(base, new, pos, exclude):
    per = {"src": [], "proj": [], "blend": [], "other_pos_proj": []}
    pct = []
    for i, b in base.items():
        if i == exclude:
            continue
        n = new.get(i)
        if n is None:
            continue
        for key in ("src", "proj", "blend"):
            bv, nv = b[key], n[key]
            if bv is None or nv is None:
                continue
            d = abs(nv - bv)
            if b["pos"] == pos:
                per[key].append(d)
                if key == "src" and bv >= 1.0:
                    pct.append(d / bv)
            elif key == "proj":
                per["other_pos_proj"].append(d)
    def summ(xs):
        return {"moved": sum(1 for x in xs if x > MOVE_EPS), "max": round(max(xs, default=0.0), 3),
                "sum": round(sum(xs), 2)}
    out = {k: summ(v) for k, v in per.items()}
    out["src"]["max_pct"] = round(100 * max(pct, default=0.0), 1)
    return out


def rank_changes(base, new, pos, exclude, key="proj"):
    def order(snap):
        rows = [(i, r[key]) for i, r in snap.items() if r["pos"] == pos and r[key] is not None and i != exclude]
        rows.sort(key=lambda t: (-t[1], t[0]))
        return {i: k for k, (i, _) in enumerate(rows)}
    a, b = order(base), order(new)
    return sum(1 for i in a if i in b and a[i] != b[i])


def set_ppg(inp, key, src, scoring, value):
    field = vr.PPG_FIELD[src]
    rec = inp.players[key].get(field)
    if rec is None:
        rec = inp.players[key][field] = {}
    old = rec.get(scoring)
    rec[scoring] = value
    return old


def prior_lines(inp, scoring, teams, prior_ppg):
    """Each rule's line on last week's projections (same league)."""
    p_inp = copy.deepcopy(inp)
    for src, vals in prior_ppg.items():
        field = vr.PPG_FIELD[src]
        for k, rec in p_inp.players.items():
            rec[field] = dict(rec.get(field) or {})
            rec[field][scoring] = vals.get(k)
    out = {}
    for base in ("current", "avg_band_3"):
        _STATE["rule"] = base
        _, res = run(p_inp, scoring, teams)
        for src in PROJ:
            if src not in res["sources"]:
                continue
            for pos in vr.POSITIONS:
                lst = sorted((x for k, x in vr.Setting(p_inp, scoring, teams).natives(src).items()
                              if p_inp.players[k]["pos"] == pos), reverse=True)
                n = (res["sources"][src]["positions"].get(pos) or {}).get("rostered")
                if n is not None and len(lst) > n:
                    out[(src, pos, base)] = RULES[base](lst, n)
    _STATE["rule"] = "current"
    return out


def load_week_ppg(week, inp):
    path = HISTORY_DIR / f"week-{week}.json"
    if not path.exists():
        return None
    h = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for src in PROJ:
        entry = (h.get("sources") or {}).get(src)
        if not entry:
            continue
        out[src] = {sc: vr.snapshot_natives(inp, src, entry, sc) for sc in SCORINGS}
    return out


# ---------------------------------------------------------------------------
# Main sweep.
# ---------------------------------------------------------------------------
def perturbation_sweep(inp, current_week, rules, combos):
    prev = load_week_ppg(current_week - 1, inp)
    results = []
    for scoring, teams in combos:
        prior = None
        if prev:
            prior = prior_lines(inp, scoring, teams, {s: v[scoring] for s, v in prev.items()})
        for rule in rules:
            _STATE["rule"], _STATE["prior"] = rule, prior
            s, base_res = run(inp, scoring, teams)
            for src in PROJ:
                if src not in base_res["sources"]:
                    continue
                natives = s.natives(src)
                lines = lines_of(base_res, src)
                base_snap = snapshot(base_res, src)
                for pos in vr.POSITIONS:
                    info = lines[pos]
                    n = info.get("rostered")
                    work = sorted(((k, x) for k, x in natives.items() if inp.players[k]["pos"] == pos),
                                  key=lambda t: (-t[1], t[0]))
                    if n is None or len(work) <= n or info.get("method") != "roster_determined":
                        results.append({"scoring": scoring, "teams": teams, "rule": rule, "source": src,
                                        "pos": pos, "skipped": info.get("method") or "no line"})
                        continue
                    targets = [("waiver", work[n][0], DELTAS), ("star", work[0][0], STAR_DELTAS)]
                    for kind, key, deltas in targets:
                        x0 = inp.ppg(key, vr.PPG_FIELD[src], scoring)
                        for d in deltas:
                            old = set_ppg(inp, key, src, scoring, max(0.0, x0 + d))
                            try:
                                _, new_res = run(inp, scoring, teams)
                            finally:
                                set_ppg(inp, key, src, scoring, old)
                            new_line = lines_of(new_res, src)[pos].get("waiver_value")
                            new_snap = snapshot(new_res, src)
                            results.append({
                                "scoring": scoring, "teams": teams, "rule": rule, "source": src,
                                "pos": pos, "target": kind, "player_key": key,
                                "player": inp.players[key].get("name") or inp.players[key].get("full_name"),
                                "native": round(x0, 3), "delta": d, "rostered": n,
                                "line_before": round(info["waiver_value"], 3),
                                "line_after": round(new_line, 3) if new_line is not None else None,
                                "effect": diff(base_snap, new_snap, pos, key),
                                "rank_changes_proj": rank_changes(base_snap, new_snap, pos, key),
                            })
        _STATE["rule"], _STATE["prior"] = "current", None
    return results


def level_shift(inp, current_week, rules, combos):
    """How far each rule moves today's values relative to the current rule
    (the one-time repricing a switch would cause)."""
    prev = load_week_ppg(current_week - 1, inp)
    out = []
    for scoring, teams in combos:
        prior = prior_lines(inp, scoring, teams, {s: v[scoring] for s, v in prev.items()}) if prev else None
        _STATE["rule"], _STATE["prior"] = "current", None
        _, cur = run(inp, scoring, teams)
        for rule in rules:
            if rule == "current":
                continue
            _STATE["rule"], _STATE["prior"] = rule, prior
            _, alt = run(inp, scoring, teams)
            for src in PROJ:
                if src not in cur["sources"]:
                    continue
                a, b = snapshot(cur, src), snapshot(alt, src)
                for pos in vr.POSITIONS:
                    la = lines_of(cur, src)[pos].get("waiver_value")
                    lb = lines_of(alt, src)[pos].get("waiver_value")
                    d = diff(a, b, pos, None)
                    out.append({"scoring": scoring, "teams": teams, "rule": rule, "source": src, "pos": pos,
                                "line_current": la, "line_rule": lb, "effect": d,
                                "rank_changes_proj": rank_changes(a, b, pos, None)})
        _STATE["rule"], _STATE["prior"] = "current", None
    return out


def weekly_stability(inp, combos):
    """Each rule's line on every saved week, at the current setting's
    rostered counts (isolates the line rule from allocation changes)."""
    weeks = sorted(int(p.stem.split("-")[1]) for p in HISTORY_DIR.glob("week-*.json"))
    snaps = {w: load_week_ppg(w, inp) for w in weeks}
    out = []
    for scoring, teams in combos:
        _STATE["rule"] = "current"
        _, res = run(inp, scoring, teams)
        for src in PROJ:
            if src not in res["sources"]:
                continue
            for pos in vr.POSITIONS:
                n = (res["sources"][src]["positions"].get(pos) or {}).get("rostered")
                if n is None:
                    continue
                series = {}
                for w in weeks:
                    vals = ((snaps.get(w) or {}).get(src) or {}).get(scoring) or {}
                    lst = sorted((x for k, x in vals.items() if inp.players[k]["pos"] == pos), reverse=True)
                    if len(lst) <= n + 5:
                        continue
                    line = {r: RULES[r](lst, n) for r in RULES}
                    series[w] = line
                ws = sorted(series)
                rec = {"scoring": scoring, "teams": teams, "source": src, "pos": pos, "rostered": n,
                       "weeks": ws, "lines": {r: [round(series[w][r], 3) for w in ws] for r in RULES}}
                rec["mean_abs_week_change"] = {}
                for r in list(RULES) + ["time_2wk", "avg_band_3_time"]:
                    if r in RULES:
                        xs = [series[w][r] for w in ws]
                    else:
                        base = "current" if r == "time_2wk" else "avg_band_3"
                        raw = [series[w][base] for w in ws]
                        xs = [0.5 * (raw[i] + raw[i - 1]) for i in range(1, len(raw))]
                    steps = [abs(xs[i] - xs[i - 1]) for i in range(1, len(xs))]
                    rec["mean_abs_week_change"][r] = round(statistics.fmean(steps), 3) if steps else None
                out.append(rec)
    return out


# ---------------------------------------------------------------------------
# Readout.
# ---------------------------------------------------------------------------
def summarize(pert, level, stab, meta):
    lines = [f"# JEG-1047 waiver-line sensitivity ({meta['generated']})", "",
             f"Inputs: `data/fixtures/current` built {meta['fixture_built_at']}, content week "
             f"{meta['current_week']}; prior-week lines from `data/history/week-{meta['current_week'] - 1}.json`. "
             f"Engine: Python reference (`pipelines/value_reference.py`) at {meta['git_head']}. "
             "Candidate rules are hypothetical and applied to the three projection sources only.", "",
             f"Source state at this build: {meta['source_state']}.", ""]
    rows = [r for r in pert if not r.get("skipped")]

    def agg(sel):
        if not sel:
            return None
        return {
            "cases": len(sel),
            "median_moved": statistics.median(r["effect"]["src"]["moved"] for r in sel),
            "p90_max": round(sorted(r["effect"]["src"]["max"] for r in sel)[int(0.9 * (len(sel) - 1))], 2),
            "worst_max": round(max(r["effect"]["src"]["max"] for r in sel), 2),
            "worst_pct": max(r["effect"]["src"]["max_pct"] for r in sel),
            "proj_worst": round(max(r["effect"]["proj"]["max"] for r in sel), 2),
            "rank_med": statistics.median(r["rank_changes_proj"] for r in sel),
            "blend_worst": round(max(r["effect"]["blend"]["max"] for r in sel), 3),
        }

    lines += ["## 1. One-player perturbation, waiver-line player, +/-1 PPG", "",
              "Each case moves only the waiver-line player's projection by 1 PPG and measures every other "
              "player at that position in that source's Adjusted value. 'Moved' = changed by more than 0.05.", "",
              "| Rule | Cases | Median others moved | 90th pct biggest move | Worst move | Worst move % | Worst DDF Projections move | Median rank changes | Worst DDF Value move |",
              "|---|---|---|---|---|---|---|---|---|"]
    for rule in meta["rules"]:
        a = agg([r for r in rows if r["rule"] == rule and r["target"] == "waiver" and abs(r["delta"]) == 1.0])
        if a:
            lines.append(f"| {RULE_LABEL[rule]} | {a['cases']} | {a['median_moved']} | {a['p90_max']} | {a['worst_max']} | "
                         f"{a['worst_pct']}% | {a['proj_worst']} | {a['rank_med']} | {a['blend_worst']} |")
    # Tolerance pass rates: share of waiver-line +/-1 PPG cases where no other
    # player at the position moves more than the tolerance.
    star_worst = {}
    for r in rows:
        if r["target"] == "star":
            k = (r["rule"], r["scoring"], r["teams"], r["source"], r["pos"])
            star_worst[k] = max(star_worst.get(k, 0.0), r["effect"]["src"]["max"])
    lines += ["", "### Pass rates against candidate tolerances (waiver-line player, +/-1 PPG)", "",
              "A case passes when no other player at the position moves more than the tolerance in that "
              "source's Adjusted value. 'No special leverage' = no bigger than the same source and position's "
              "move when its top player changes by 1 PPG.", "",
              "| Rule | <= 0.25 pts | <= 0.5 pts | <= 0.5 pts and <= 10% | <= 1.0 pts | No special leverage |",
              "|---|---|---|---|---|---|"]
    for rule in meta["rules"]:
        sel = [r for r in rows if r["rule"] == rule and r["target"] == "waiver" and abs(r["delta"]) == 1.0]
        if not sel:
            continue
        def rate(fn):
            return f"{round(100 * sum(1 for r in sel if fn(r)) / len(sel))}%"
        lines.append(f"| {RULE_LABEL[rule]} | {rate(lambda r: r['effect']['src']['max'] <= 0.25)} | "
                     f"{rate(lambda r: r['effect']['src']['max'] <= 0.5)} | "
                     f"{rate(lambda r: r['effect']['src']['max'] <= 0.5 and r['effect']['src']['max_pct'] <= 10)} | "
                     f"{rate(lambda r: r['effect']['src']['max'] <= 1.0)} | "
                     f"{rate(lambda r: r['effect']['src']['max'] <= star_worst.get((r['rule'], r['scoring'], r['teams'], r['source'], r['pos']), 0.0) + 1e-9)} |")
    lines += ["", "## 2. Current rule, by source and position (waiver-line player, +/-1 PPG)", "",
              "| Source | Pos | Cases | Median others moved | Worst move | Worst move % | Worst DDF Projections move |",
              "|---|---|---|---|---|---|---|"]
    for src in PROJ:
        for pos in vr.POSITIONS:
            sel = [r for r in rows if r["rule"] == "current" and r["target"] == "waiver" and abs(r["delta"]) == 1.0
                   and r["source"] == src and r["pos"] == pos]
            a = agg(sel)
            if a:
                lines.append(f"| {SRC_LABEL[src]} | {pos} | {a['cases']} | {a['median_moved']} | {a['worst_max']} | "
                             f"{a['worst_pct']}% | {a['proj_worst']} |")
    lines += ["", "## 3. Control: the top player at the position, +/-1 PPG (current rule)", "",
              "| Source | Pos | Median others moved | Worst move |", "|---|---|---|---|"]
    for src in PROJ:
        for pos in vr.POSITIONS:
            sel = [r for r in rows if r["rule"] == "current" and r["target"] == "star" and r["source"] == src and r["pos"] == pos]
            a = agg(sel)
            if a:
                lines.append(f"| {SRC_LABEL[src]} | {pos} | {a['median_moved']} | {a['worst_max']} |")
    lines += ["", "## 4. Worst single cases under the current rule", "",
              "| Setting | Source | Pos | Player (native PPG) | Change | Line before -> after | Others moved | Worst move | Worst % |",
              "|---|---|---|---|---|---|---|---|---|"]
    worst = sorted((r for r in rows if r["rule"] == "current" and r["target"] == "waiver"),
                   key=lambda r: -r["effect"]["src"]["max"])[:12]
    for r in worst:
        lines.append(f"| {r['scoring']}/{r['teams']} | {SRC_LABEL[r['source']]} | {r['pos']} | {r['player']} ({r['native']}) | "
                     f"{r['delta']:+} | {r['line_before']} -> {r['line_after']} | {r['effect']['src']['moved']} | "
                     f"{r['effect']['src']['max']} | {r['effect']['src']['max_pct']}% |")
    lines += ["", "## 5. One-time repricing if a rule replaced the current one (today's data)", "",
              "| Rule | Cells | Median players moved per cell | Worst move | Median line change (PPG) | Median rank changes |",
              "|---|---|---|---|---|---|"]
    for rule in meta["rules"]:
        sel = [r for r in level if r["rule"] == rule and r["line_current"] is not None and r["line_rule"] is not None]
        if sel:
            lines.append(f"| {RULE_LABEL[rule]} | {len(sel)} | {statistics.median(r['effect']['src']['moved'] for r in sel)} | "
                         f"{round(max(r['effect']['src']['max'] for r in sel), 2)} | "
                         f"{round(statistics.median(r['line_rule'] - r['line_current'] for r in sel), 3)} | "
                         f"{statistics.median(r['rank_changes_proj'] for r in sel)} |")
    lines += ["", "## 6. Week-to-week line movement on saved weeks", "",
              "Mean absolute week-over-week change in the line (PPG), at the current settings' rostered counts.", "",
              "| Rule | All cells | QB | RB | WR | TE |", "|---|---|---|---|---|---|"]
    for rule in list(RULES) + ["time_2wk", "avg_band_3_time"]:
        def m(sel):
            xs = [r["mean_abs_week_change"][rule] for r in sel if r["mean_abs_week_change"].get(rule) is not None]
            return round(statistics.fmean(xs), 3) if xs else "n/a"
        lines.append(f"| {RULE_LABEL[rule]} | {m(stab)} | " + " | ".join(str(m([r for r in stab if r['pos'] == p])) for p in vr.POSITIONS) + " |")
    skipped = sorted({(r['source'], r['pos'], r['skipped'], r['scoring'], r['teams']) for r in pert if r.get('skipped') and r['rule'] == 'current'})
    if skipped:
        lines += ["", "## Cells with no single-player line (not tested)", ""]
        for s in skipped:
            lines.append(f"- {SRC_LABEL[s[0]]} {s[1]} at {s[3]}/{s[4]}: {s[2]}")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="PPR 12 teams only")
    ap.add_argument("--readout-only", action="store_true", help="rebuild the .md from the saved .json")
    args = ap.parse_args(argv)
    if args.readout_only:
        d = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        OUT_MD.write_text(summarize(d["perturbations"], d["level_shift"], d["weekly_stability"], d["meta"]), encoding="utf-8")
        print(f"wrote {OUT_MD.relative_to(REPO)}")
        return
    t0 = time.time()
    _install_patch()
    inp = vr.Inputs.load()
    fresh = vr.freshness(inp)
    current_week = fresh["current_week"]
    combos = [("ppr", 12)] if args.quick else [(s, t) for s in SCORINGS for t in TEAMS]
    rules = list(RULES) + ["time_2wk", "avg_band_3_time"]
    st = vr.Setting(inp, "ppr", 12).state()
    import subprocess
    head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    meta = {"generated": time.strftime("%Y-%m-%d", time.gmtime()), "fixture_built_at": inp.fixture.get("built_at"),
            "current_week": current_week, "git_head": head, "rules": rules,
            "source_state": ", ".join(f"{SRC_LABEL[k]} {st['excluded'].get(k, 'included')}" for k in PROJ)}
    pert = perturbation_sweep(inp, current_week, rules, combos)
    level = level_shift(inp, current_week, rules, combos)
    stab = weekly_stability(inp, combos)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"meta": meta, "perturbations": pert, "level_shift": level,
                                    "weekly_stability": stab}, separators=(",", ":"), default=str), encoding="utf-8")
    OUT_MD.write_text(summarize(pert, level, stab, meta), encoding="utf-8")
    print(f"wrote {OUT_JSON.relative_to(REPO)} and {OUT_MD.relative_to(REPO)} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
