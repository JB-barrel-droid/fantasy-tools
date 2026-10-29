#!/usr/bin/env python3
"""Recompute every number quoted in research post 9 (position weights, JEG-925).

Runs the Python reference (pipelines/value_reference.py) on the current fixture
and writes one JSON with the weights, budgets, per-source mixes, the league
size / scoring / superflex / bench / two-TE sweeps, leave-one-out (a real
drop-out and the averaging step alone) and the 5-point RB/WR shift.

It refuses (exit 2) when any of the seven sources is excluded at PPR/12, e.g.
the week-8 transition on 2026-10-27, when the four charts were "not yet
published for week 8" and the weights came from the projections alone
(JEG-1175). Quoting that state would publish an outage as the method.
Pass --allow-partial to write the numbers anyway (for diagnosis only).

    python3 tools/research_post9_numbers.py [--out PATH] [--allow-partial]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pipelines.value_reference as vr  # noqa: E402
from pipelines.value_reference import POSITIONS, Inputs, Setting  # noqa: E402

SEVEN = ("usatoday", "fantasycalc", "fantasypros", "cbs", "espn", "cbsros", "razzball")


def pct(x: float) -> float:
    return round(100 * x, 1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="/tmp/research_post9_numbers.json")
    ap.add_argument("--allow-partial", action="store_true")
    args = ap.parse_args(argv)

    inp = Inputs.load()
    base_roster = dict(vr.DEFAULT_ROSTER)

    def run(roster: dict | None = None, **kw):
        vr.DEFAULT_ROSTER.update(base_roster)
        vr.DEFAULT_ROSTER.update(roster or {})
        try:
            s = Setting(inp, **kw)
            return s, s.result()
        finally:
            vr.DEFAULT_ROSTER.clear()
            vr.DEFAULT_ROSTER.update(base_roster)

    def totals(r: dict) -> dict:
        w = r["ddf_weights"]
        t = {p: pct(w[f"{p}|starter"] + w[f"{p}|bench"]) for p in POSITIONS}
        t["bench"] = pct(sum(w[f"{p}|bench"] for p in POSITIONS))
        return t

    s, r = run(scoring="ppr", teams=12)
    missing = [k for k in SEVEN if k not in r["included"]]
    out: dict = {"included": r["included"], "excluded": s._state["excluded"]}
    if missing and not args.allow_partial:
        print(f"refusing: {', '.join(missing)} not included at PPR/12 "
              f"({s._state['excluded']}); rerun when every source publishes "
              "or pass --allow-partial", file=sys.stderr)
        return 2

    w = r["ddf_weights"]
    out.update({
        "weight_sum": round(sum(w.values()), 6),
        "pie": r["pie"],
        "weights": {k: pct(v) for k, v in w.items()},
        "totals": totals(r),
        "budgets": {k: round(v, 1) for k, v in r["group_budgets"].items()},
        "slot_fill": r["slot_fill"],
        "starter_mix_mean": {k: pct(v) for k, v in r["starter_mix_mean"].items()},
        "bench_mix_mean": {k: pct(v) for k, v in r["bench_mix_mean"].items()},
        "sources": {k: {"family": d.get("family"), "status": d.get("status"),
                        "groups": {g: round(v, 1) for g, v in (d.get("groups") or {}).items()},
                        "starter_mix": {p: pct(v) for p, v in (d.get("starter_mix") or {}).items()},
                        "bench_mix": {p: pct(v) for p, v in (d.get("bench_mix") or {}).items()},
                        "weights": {g: pct(v) for g, v in (d.get("weights") or {}).items()}}
                    for k, d in r["sources"].items()},
        "teams": {t: totals(run(scoring="ppr", teams=t)[1]) for t in (8, 10, 12, 14)},
        "scoring": {sc: totals(run(scoring=sc, teams=12)[1]) for sc in ("half_ppr", "standard")},
        "bench_size": {b: totals(run(roster={"BENCH": b}, scoring="ppr", teams=12)[1]) for b in (4, 10)},
        # JEG-1142: the promotion model is off by its master switch, so the
        # weights quoted are the switch-off weights; record the switch.
        "promotion_model_enabled": vr.PROMOTION_MODEL_ENABLED,
    })
    _, sf = run(scoring="ppr", teams=12, superflex=1)
    out["superflex"], out["superflex_pie"] = totals(sf), sf["pie"]
    _, te2 = run(roster={"TE": 2}, scoring="ppr", teams=12)
    out["two_te"], out["two_te_pie"] = totals(te2), te2["pie"]
    # Leave one source out (JEG-1349). "leave_one_out" is a real drop-out:
    # the source leaves `included` and the whole pipeline reruns, so the
    # shared allocation (mean projected points over the included
    # projections), the chart fill-ins and every other source's group totals
    # move with it, as when a source fails to publish. "leave_one_out_
    # averaging_only" keeps those fixed and re-averages the remaining
    # sources' existing 8-group weights (VP-4 / ES-15.1), which isolates the
    # averaging step alone.
    def drop_out(keep: list) -> dict:
        st = s.state()
        return vr.run_pipeline(s.league, s._sources(st["current"]), s.pos_of, keep,
                               s.selection, lineup=s.lineup, hidden=st.get("hidden"),
                               promotion_model=s.promotion_model,
                               flex_bench_seats=s.flex_bench_seats, basis=s.basis)

    def averaging_only(keep: list) -> dict:
        return {"ddf_weights": vr.ddf_weights(s.league, r["sources"], keep,
                                              computed_share=True)["weights"]}

    for name, fn in (("drop-out", drop_out), ("averaging-only", averaging_only)):
        full = fn(list(r["included"]))["ddf_weights"]
        if max(abs(full[g] - w[g]) for g in w) > 1e-9:
            print(f"refusing: the {name} rerun with every source kept does not "
                  "reproduce the pipeline's weights", file=sys.stderr)
            return 2
    others = {k: [x for x in r["included"] if x != k] for k in r["included"]}
    out["leave_one_out"] = {k: totals(drop_out(keep)) for k, keep in others.items()}
    out["leave_one_out_averaging_only"] = {k: totals(averaging_only(keep)) for k, keep in others.items()}

    # Sensitivity: move 5 points of the pie from WR to RB; ratio of each
    # player's blended DDF Value after / before, by position.
    shares = {p: (w[f"{p}|starter"] + w[f"{p}|bench"]) for p in POSITIONS}
    shares["RB"] += 0.05
    shares["WR"] -= 0.05
    _, r2 = run(scoring="ppr", teams=12, position_shares=shares)
    ratios: dict[str, list[float]] = {}
    for i, row in r["rows"].items():
        a = row["ddf"]["blended"]["value"]
        b = ((r2["rows"].get(i) or {}).get("ddf", {}).get("blended") or {}).get("value")
        if a and b and a > 1:
            ratios.setdefault(row["pos"], []).append(b / a)
    out["shift_5pt_wr_to_rb"] = {p: {"min": round(min(v), 4), "max": round(max(v), 4), "n": len(v)}
                                 for p, v in ratios.items()}

    Path(args.out).write_text(json.dumps(out, indent=1, default=str))
    print(f"wrote {args.out} ({'partial: ' + ', '.join(missing) + ' excluded' if missing else 'all seven sources'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
