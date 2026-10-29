"""JEG-1336 research: a chart estimate that steps in and out at the rostered cutoff.

Research only. Runs the Python reference (pipelines/value_reference.py) of a
checkout given by --repo, with `run_pipeline` rebuilt in-process from its own
source so two lines become hooks:

  fill set   VP-2.4a, `Fill_p` = the first N_p + 1 players of the projected
             order (the players a chart must estimate if it doesn't list them)
  estimates  after a chart's estimates at one position are made, before they
             join its work list (VP-2.3)

With the default hooks the rebuilt pipeline is checked equal to the reference
on every setting before anything runs. Nothing in the pipeline, config or
published output changes. The allocation (VP-2.2) is held wherever a step is
measured, so flex and bench flips (JEG-1286 / JEG-1333) are not counted here.

Options (docs/research/jeg1336-fill-in.md explains each):

  A   today's rule
  B   fractional fill-in: each player near the cutoff holds a share
      Phi((m - c) / sigma) of a fill-set place, sigma 0.75 PPG (as JEG-1333),
      and every chart estimate is scaled by that share
  C   estimate every player at least one included chart lists, at any depth;
      players no chart lists are never estimated
  D   order cap: a curve-path estimate (VP-2.4e, no chart lists him) is never
      worth more on that chart than a player the projections rank above him
  BD  B and D together

Experiments:

  today     every setting's values under each option; one-time change vs A
  sweep     +-0.5 and +-1 PPG to one projection for each player within 3 of a
            fill cutoff, allocation held: largest move of any other player
  history   every players.json bake on main replayed with today's code: how
            often fill-set membership changes between two consecutive bakes,
            and how far DDF Value moves when only the membership changes

Usage:
  python3 tools/research/jeg1336_fill_in.py --repo . --out docs/research/data
"""
from __future__ import annotations

import argparse
import inspect
import json
import math
import subprocess
import sys
import tempfile
import textwrap
from datetime import timedelta, timezone
from multiprocessing import Pool
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent))
import jeg1286_flex_flips as F  # noqa: E402

SIGMA = 0.75          # PPG, the measured projection disagreement (JEG-1286 section 1)
SHARE_MIN = 1e-3      # B: players with a smaller share are left out of the fill set
BAND = 3              # players either side of a fill cutoff that the sweep perturbs
DELTAS = (-1.0, -0.5, 0.5, 1.0)
OPTIONS = ("A", "B", "C", "D", "BD")
NAMED = ("Chris Brooks", "Raheim Sanders", "CJ Donaldson", "DJ Herman")

VR = None
CTX = {"opt": "A", "held": None, "shares": {}, "fill_out": None, "capped": []}

FILL_LINE = 'fill_sets = {} if degenerate else {p: order_m[p][:alloc[p]["rostered"] + 1] for p in POSITIONS}'
FILL_HOOK = "fill_sets = _J1336_FILL(order_m, alloc, degenerate, sources, inc, pos_of, m)"
EST_LINE = "                if est:\n                    estimates[p] = est"
EST_HOOK = "                est = _J1336_EST(src, p, est, own_order[p], m, pos_of)\n" + EST_LINE


def setup(repo):
    """Load the reference and rebuild run_pipeline with the two hooks."""
    global VR
    vr, _ = F.setup(Path(repo))
    VR = vr
    if getattr(vr, "_J1336_ORIG", None) is None:
        src = textwrap.dedent(inspect.getsource(vr.run_pipeline))
        if src.count(FILL_LINE) != 1 or src.count(EST_LINE) != 1:
            raise SystemExit("run_pipeline no longer has the VP-2.4 lines this script hooks")
        ns = vr.__dict__
        ns["_J1336_SAVED"] = vr.run_pipeline
        exec(compile(src.replace(FILL_LINE, FILL_HOOK).replace(EST_LINE, EST_HOOK),
                     vr.__file__, "exec"), ns)
        vr._J1336_ORIG = vr.__dict__["run_pipeline"]
        ns["_J1336_FILL"] = fill_hook
        ns["_J1336_EST"] = est_hook
    return vr


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------

def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def fill_today(order_m, alloc):
    return {p: order_m[p][:alloc[p]["rostered"] + 1] for p in VR.POSITIONS}


def fill_shares(order_m, alloc, m):
    """B: share of a fill-set place for each player near the cutoff. The
    cutoff sits halfway between the last player in today's fill set and the
    first one out."""
    out = {}
    for p in VR.POSITIONS:
        order, n = order_m[p], alloc[p]["rostered"] + 1
        if len(order) <= n:
            out[p] = {i: 1.0 for i in order}
            continue
        c = 0.5 * (m[order[n - 1]] + m[order[n]])
        sh = {}
        for i in order:
            s = _phi((m[i] - c) / SIGMA)
            if s >= SHARE_MIN:
                sh[i] = s
        out[p] = sh
    return out


def fill_listed(order_m, alloc, sources, inc, pos_of):
    """C: every projected player at p that at least one included chart lists
    (a player with no projection has no mean PPG for the curve path)."""
    listed = {p: set() for p in VR.POSITIONS}
    for k in inc:
        if sources[k].family != "chart":
            continue
        for i in sources[k].values:
            if pos_of.get(i) in listed:
                listed[pos_of[i]].add(i)
    out = {}
    for p in VR.POSITIONS:
        out[p] = [i for i in order_m[p] if i in listed[p]]
    return out


def fill_hook(order_m, alloc, degenerate, sources, inc, pos_of, m):
    if degenerate:
        CTX["fill_out"], CTX["shares"] = {}, {}
        return {}
    opt, held = CTX["opt"], CTX["held"]
    if opt in ("B", "BD"):
        shares = fill_shares(order_m, alloc, m)
        fs = {p: list(shares[p]) for p in VR.POSITIONS}
    elif opt == "C":
        shares = {}
        fs = fill_listed(order_m, alloc, sources, inc, pos_of)
    else:
        shares = {}
        fs = fill_today(order_m, alloc)
    CTX["fill_out"] = {"fill": {p: list(v) for p, v in fs.items()},
                       "shares": {p: dict(v) for p, v in shares.items()},
                       "m": sorted(m)}
    if held is not None:
        # The earlier bake's fill set for every player projected in both
        # bakes; a player with no projection in the earlier bake (back from
        # injury, newly added) keeps today's rule, so only cutoff crossings
        # are held.
        old_m = set(held["m"])
        fs = {p: [i for i in held["fill"].get(p, []) if pos_of.get(i) == p and i in m]
              + [i for i in fs[p] if i not in old_m] for p in VR.POSITIONS}
        shares = {p: {**{i: s for i, s in held["shares"].get(p, {}).items() if pos_of.get(i) == p and i in m},
                      **{i: s for i, s in shares.get(p, {}).items() if i not in old_m}}
                  for p in VR.POSITIONS}
    CTX["shares"] = shares
    return fs


def est_hook(src, p, est, own_order_p, m, pos_of):
    opt = CTX["opt"]
    sh = CTX["shares"].get(p) or {}
    if opt in ("B", "BD") and sh:
        for i, e in est.items():
            s = sh.get(i, 0.0)
            if s < 1.0:
                e["unshared_value"] = e["value"]
                e["share"] = s
                e["value"] = e["value"] * s
    if opt in ("D", "BD"):
        vals = {i: src.values[i] for i in own_order_p}
        vals.update({i: e["value"] for i, e in est.items()})
        low = math.inf
        for i in sorted((i for i in vals if i in m), key=lambda i: (-m[i], i)):
            e = est.get(i)
            if e is not None and e["path"] == "curve" and e["value"] > low:
                CTX["capped"].append((src.key, p, i, e["value"], low))
                e["uncapped_value"] = e["value"]
                e["value"] = low
            low = min(low, e["value"] if e is not None else vals[i])
    return est


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def run(inp, cell, opt="A", alloc_fn=None, held=None):
    """One Setting run under option `opt`. Returns (values, allocations,
    result, fill) where fill is what the fill hook used (for holding it)."""
    CTX.update({"opt": opt, "held": held, "capped": []})
    try:
        vals, made, res = F.run(inp, cell, alloc_fn)
    finally:
        CTX.update({"opt": "A", "held": None})
    return vals, made, res, CTX["fill_out"]


def check_equal(inp):
    """With option A's hooks the rebuilt pipeline must equal the reference."""
    bad = []
    for cell in F.cells():
        a, _, _, _ = run(inp, cell)
        orig = VR.run_pipeline
        VR.run_pipeline = VR.__dict__["_J1336_SAVED"]
        try:
            b, _, _ = F.run(inp, cell)
        finally:
            VR.run_pipeline = orig
        if a != b:
            bad.append(cell["name"])
    return bad


def listed_by(res, i):
    """Charts in I that list player i (have a non-estimated value)."""
    out = []
    for k in res["included"]:
        if VR.FAMILY[k] != "chart":
            continue
        rec = res["sources"][k]["players"].get(i)
        if rec is not None and not rec["imputed"]:
            out.append(k)
    return out


def top_moves(a, b, inp, n=5, skip=None):
    rows = []
    for i, ra in a.items():
        if i == skip or i not in b or ra["ddf"] is None or b[i]["ddf"] is None:
            continue
        d = b[i]["ddf"] - ra["ddf"]
        if abs(d) > 1e-9:
            rows.append((abs(d), i, ra["ddf"], b[i]["ddf"]))
    rows.sort(reverse=True)
    return [{"who": F.name(inp, i), "pos": a[i]["pos"], "before": x, "after": y} for _, i, x, y in rows[:n]]


def worst(a, b, skip=None):
    best, who = 0.0, None
    for i, ra in a.items():
        if i == skip or i not in b or ra["ddf"] is None or b[i]["ddf"] is None:
            continue
        d = abs(b[i]["ddf"] - ra["ddf"])
        if d > best:
            best, who = d, i
    return best, who


# ---------------------------------------------------------------------------
# today: values under each option, and the fill boundary
# ---------------------------------------------------------------------------

def today_cell(args):
    repo, cell = args
    setup(repo)
    inp = VR.Inputs.load()
    base = {o: run(inp, cell, o) for o in OPTIONS}
    a_vals, _, a_res, a_fill = base["A"]
    m = a_res["mean_ppg"]
    boundary = {}
    for p in VR.POSITIONS:
        order = sorted((i for i in m if inp.players.get(i, {}).get("pos") == p),
                       key=lambda i: (-m[i], i))
        n = a_res["allocation"][p]["rostered"] + 1
        rows = []
        for j in range(max(0, n - 4), min(len(order), n + 3)):
            i = order[j]
            est = (a_res["rows"][i].get("estimated") or {}) if i in a_res["rows"] else {}
            rows.append({"rank": j + 1, "who": F.name(inp, i), "mean_ppg": m[i], "in_fill": j < n,
                         "listed_by": listed_by(a_res, i), "estimated": est,
                         **{o: base[o][0].get(i, {}).get("ddf") for o in OPTIONS}})
        boundary[p] = {"fill_size": n, "rows": rows}
    depart = {}
    for o in OPTIONS[1:]:
        w, who = worst(a_vals, base[o][0])
        n_moved = sum(1 for i in a_vals if i in base[o][0] and a_vals[i]["ddf"] is not None
                      and base[o][0][i]["ddf"] is not None and abs(base[o][0][i]["ddf"] - a_vals[i]["ddf"]) > 0.1)
        depart[o] = {"worst": w, "worst_who": F.name(inp, who) if who else None, "moved_over_0.1": n_moved,
                     "top": top_moves(a_vals, base[o][0], inp, 6)}
    # Curve-path estimates that land above the chart's own waiver line.
    curve = []
    for k in a_res["included"]:
        if VR.FAMILY[k] != "chart":
            continue
        for p, info in a_res["sources"][k]["positions"].items():
            for i, e in (info.get("imputation_ratios") or {}).items():
                if e["path"] == "curve":
                    rec = a_res["sources"][k]["players"][i]
                    curve.append({"chart": k, "pos": p, "who": F.name(inp, i), "mean_ppg": m.get(i),
                                  "value": e["value"], "waiver": info["waiver_value"],
                                  "adj": a_vals[i]["adj"].get(k), "ddf": a_vals[i]["ddf"]})
    named = {}
    for i, r in a_vals.items():
        nm = F.name(inp, i)
        if nm in NAMED:
            named[nm] = {o: base[o][0][i]["ddf"] for o in OPTIONS if i in base[o][0]}
    return {"cell": cell["name"], "boundary": boundary, "departure": depart, "curve": curve, "named": named}


# ---------------------------------------------------------------------------
# sweep: one-player changes near the fill cutoff, allocation held
# ---------------------------------------------------------------------------

def sweep_cell(args):
    repo, cell = args
    setup(repo)
    inp = VR.Inputs.load()
    _, a_made, a_res, _ = run(inp, cell)
    if not a_made:
        return {"cell": cell["name"], "cases": []}
    hold = F.replay(a_made)
    m = a_res["mean_ppg"]
    keys = set()
    for p in VR.POSITIONS:
        order = sorted((i for i in m if inp.players.get(i, {}).get("pos") == p), key=lambda i: (-m[i], i))
        n = a_res["allocation"][p]["rostered"] + 1
        keys.update(order[max(0, n - BAND):min(len(order), n + BAND)])
    base = {o: run(inp, cell, o, hold)[0] for o in OPTIONS}
    cases = []
    for k in sorted(keys):
        for src in VR.PROJECTIONS:
            rec = inp.players[k].get(VR.PPG_FIELD[src])
            if not isinstance(rec, dict) or not VR._finite(rec.get(cell["scoring"])):
                continue
            old = rec[cell["scoring"]]
            for delta in DELTAS:
                rec[cell["scoring"]] = max(0.0, old + delta)
                try:
                    c = {"key": k, "name": F.name(inp, k), "pos": inp.players[k]["pos"], "src": src,
                         "delta": delta, "options": {}}
                    for o in OPTIONS:
                        vals, _, _, fill = run(inp, cell, o, hold)
                        w, who = worst(base[o], vals, skip=k)
                        c["options"][o] = {"ddf": w, "who": F.name(inp, who) if who else None,
                                           "before": base[o][who]["ddf"] if who else None,
                                           "after": vals[who]["ddf"] if who else None}
                        if o == "A":
                            c["fill_changed"] = ({p: set(v) for p, v in fill["fill"].items()}
                                                 != {p: set(v) for p, v in base_fill_a(inp, cell, hold).items()})
                finally:
                    rec[cell["scoring"]] = old
                cases.append(c)
    return {"cell": cell["name"], "cases": cases}


_BASE_FILL = {}


def base_fill_a(inp, cell, hold):
    if cell["name"] not in _BASE_FILL:
        _BASE_FILL[cell["name"]] = run(inp, cell, "A", hold)[3]["fill"]
    return _BASE_FILL[cell["name"]]


# ---------------------------------------------------------------------------
# history: real bakes, consecutive pairs
# ---------------------------------------------------------------------------

def ranks(res, inp):
    """Each player's 1-based rank in his position's projected order, and the
    fill-set size (the cutoff rank) per position."""
    m = res["mean_ppg"]
    rank, cut = {}, {}
    for p in VR.POSITIONS:
        order = sorted((i for i in m if inp.players.get(i, {}).get("pos") == p), key=lambda i: (-m[i], i))
        rank.update({i: j + 1 for j, i in enumerate(order)})
        cut[p] = res["allocation"][p]["rostered"] + 1
    return rank, cut


def history_cell(args):
    repo, cell, snaps = args
    setup(repo)
    from lib.timestamps import parse_iso_timestamp  # on the path after setup()
    rows, prev = [], None
    for sha, when, players, fixture in snaps:
        try:
            day = parse_iso_timestamp(when).astimezone(timezone(timedelta(hours=-5))).date()
            inp = VR.Inputs.load(fixture=fixture, players=players, today=day)
            cur = {o: run(inp, cell, o) for o in OPTIONS}
        except Exception as e:  # an old fixture today's code can't read
            rows.append({"sha": sha[:8], "when": when, "error": f"{type(e).__name__}: {e}"[:200]})
            prev = None
            continue
        a_vals, a_made, a_res, a_fill = cur["A"]
        n_src = len([k for k in a_res["included"] if VR.FAMILY[k] == "projection"])
        if not a_made or n_src < 3:
            rows.append({"sha": sha[:8], "when": when, "skip": "degenerate" if not a_made else f"{n_src} projections"})
            prev = None
            continue
        r = {"sha": sha[:8], "when": when}
        if prev is not None and len(prev["made"]) == len(a_made):
            hold = F.replay(prev["made"])
            ch = {}
            for p in VR.POSITIONS:
                before, after = set(prev["fill"]["A"]["fill"][p]), set(a_fill["fill"][p])
                ins, outs = sorted(after - before), sorted(before - after)
                ch[p] = {"in": [F.name(inp, i) for i in ins], "out": [F.name(inp, i) for i in outs],
                         "in_unlisted": [F.name(inp, i) for i in ins if len(listed_by(a_res, i)) < 4],
                         "in_listed_by_none": [F.name(inp, i) for i in ins if not listed_by(a_res, i)],
                         "out_listed_by_none": [F.name(inp, i) for i in outs if not listed_by(a_res, i)]}
            r["changes"] = ch
            cur_rank, cur_cut = ranks(a_res, inp)
            step = {}
            try:
                for o in OPTIONS:
                    free, _, _, _ = run(inp, cell, o, hold)
                    held, _, _, _ = run(inp, cell, o, hold, held=prev["fill"][o])
                    w, who = worst(held, free)
                    step[o] = {"ddf": w, "who": F.name(inp, who) if who else None,
                               "held": held[who]["ddf"] if who else None,
                               "free": free[who]["ddf"] if who else None,
                               "rank": cur_rank.get(who), "prev_rank": prev["rank"].get(who),
                               "cutoff": cur_cut.get(a_vals[who]["pos"]) if who else None,
                               "mean_change": (a_res["mean_ppg"][who] - prev["m"][who])
                               if who in a_res["mean_ppg"] and who in prev["m"] else None}
                r["step"] = step
            except Exception as e:  # a held fill set today's code can't price
                r["step_error"] = f"{type(e).__name__}: {e}"[:200]
        rows.append(r)
        prev = {"made": a_made, "fill": {o: cur[o][3] for o in OPTIONS},
                "m": dict(a_res["mean_ppg"]), "rank": ranks(a_res, inp)[0]}
    return {"cell": cell["name"], "bakes": rows}


# ---------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE.parents[2]))
    ap.add_argument("--git", default=None, help="repo whose git history to replay (default --repo)")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--out", default=None)
    ap.add_argument("--only", default="today,sweep,history")
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args(argv)
    repo = Path(a.repo).resolve()
    vr = setup(repo)
    out_dir = Path(a.out or repo / "docs" / "research" / "data")
    out_dir.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(","))
    report = {"repo_head": subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                                          capture_output=True, text=True).stdout.strip(),
              "sigma": SIGMA, "options": OPTIONS}
    bad = check_equal(vr.Inputs.load())
    if bad:
        raise SystemExit(f"hooked run_pipeline differs from value_reference on {bad}")
    report["hook_check"] = "hooked run_pipeline (option A) == value_reference.run_pipeline on every cell"
    cells = F.cells()
    path = out_dir / "jeg1336_fill_in.json"

    def dump():
        path.write_text(json.dumps(report, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")

    with Pool(a.procs) as pool:
        if "today" in only:
            report["today"] = pool.map(today_cell, [(str(repo), c) for c in cells])
            dump()
        if "sweep" in only:
            report["sweep"] = pool.map(sweep_cell, [(str(repo), c) for c in cells])
            dump()
        if "history" in only:
            with tempfile.TemporaryDirectory() as td:
                snaps = F.snapshots(Path(a.git or repo), a.ref, Path(td))
                report["history"] = pool.map(history_cell, [(str(repo), c, snaps) for c in cells])
    dump()
    print(path)


if __name__ == "__main__":
    main()
