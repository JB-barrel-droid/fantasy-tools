#!/usr/bin/env python3
"""Three-way diff of the value pipeline on live data (JEG-508 VP-12, JEG-536 ES-11).

Reads the two dumps `pipelines/value_check.py compare` writes (the engine,
output/value-check-engine.json, and the Python reference,
output/value-check-reference.json) and runs the clean-room spec reference
(pipelines/spec_reference/pipeline_live.py) on the same snapshot. For every
setting it compares, between each pair, every source's value in each tab, the
three DDF versions and the bench-share readout (ES-14), at value_check's
tolerance (0.05; the readout to 0.0005, i.e. 0.05 percentage points).

    python3 pipelines/value_check.py compare     # writes the two dumps
    python3 tools/value_three_way.py [--out output/value-three-way.json]

Exit 1 when any pair disagrees.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

TOL = 0.05
READOUT_TOL = 0.0005
VIEW_MAP = {"indexed": "indexed", "vorp": "vorp", "adj": "adjusted"}
READOUT_KEYS = ("QB", "RB", "WR", "TE", "overall")


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def diff_maps(a: dict, b: dict, tol: float) -> dict:
    """{player: value} vs {player: value}: presence must match, numbers within tol."""
    keys = set(a) | set(b)
    out = {"compared": 0, "mismatches": 0, "max_abs_diff": 0.0, "examples": []}
    for k in sorted(keys, key=lambda x: int(x)):
        x, y = _num(a.get(k)), _num(b.get(k))
        out["compared"] += 1
        if x is None and y is None:
            continue
        if x is None or y is None:
            out["mismatches"] += 1
            if len(out["examples"]) < 3:
                out["examples"].append({"player": k, "a": a.get(k), "b": b.get(k)})
            continue
        d = abs(x - y)
        out["max_abs_diff"] = max(out["max_abs_diff"], d)
        if d > tol:
            out["mismatches"] += 1
            if len(out["examples"]) < 3:
                out["examples"].append({"player": k, "a": x, "b": y})
    return out


def series_of(views: dict, view: str, series: str) -> dict:
    """{player: value} for one series from an engine/reference dump's rows."""
    rows = views.get(view) or {}
    return {k: r.get(series) for k, r in rows.items() if series in r}


def readout_of(pipeline: dict | None) -> dict | None:
    if not pipeline:
        return None
    r = pipeline.get("benchShare") if "benchShare" in pipeline else pipeline.get("bench_share_readout")
    return r if isinstance(r, dict) else None


def compare_readouts(a: dict | None, b: dict | None) -> dict:
    if a is None or b is None:
        return {"mismatches": 0 if a is None and b is None else 1, "max_abs_diff": None}
    worst, bad = 0.0, 0
    for k in READOUT_KEYS:
        x, y = _num(a.get(k)), _num(b.get(k))
        if x is None or y is None:
            bad += 0 if x is None and y is None else 1
            continue
        worst = max(worst, abs(x - y))
        bad += abs(x - y) > READOUT_TOL
    return {"mismatches": bad, "max_abs_diff": worst}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--engine", type=Path, default=REPO / "output" / "value-check-engine.json")
    ap.add_argument("--reference", type=Path, default=REPO / "output" / "value-check-reference.json")
    ap.add_argument("--out", type=Path, default=REPO / "output" / "value-three-way.json")
    args = ap.parse_args(argv)
    from spec_reference import pipeline_live

    engine = json.loads(args.engine.read_text(encoding="utf-8"))["settings"]
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    spec = pipeline_live.build()["settings"]
    report = {"tolerance": TOL, "readout_tolerance": READOUT_TOL, "settings": {}, "totals": {}}
    totals = report["totals"]
    for sid, eng in engine.items():
        ref = reference.get(sid)
        sp = spec.get(sid)
        cell = {}
        for view, spec_view in VIEW_MAP.items():
            rows = eng["views"].get(view) or {}
            series_names = set().union(*(set(r) for r in rows.values())) if rows else set()
            for series in sorted(series_names):
                if series.endswith("_count"):
                    continue
                e = series_of(eng["views"], view, series)
                r = series_of(ref["views"], view, series) if ref else {}
                s = (sp["values"].get(spec_view) or {}).get(series) if sp else None
                pairs = {"engine~reference": diff_maps(e, r, TOL)}
                if s is not None:
                    pairs["engine~spec"] = diff_maps(e, s, TOL)
                    pairs["reference~spec"] = diff_maps(r, s, TOL)
                cell[f"{view}:{series}"] = pairs
                for pair, d in pairs.items():
                    t = totals.setdefault(pair, {"compared": 0, "mismatches": 0, "max_abs_diff": 0.0})
                    t["compared"] += d["compared"]
                    t["mismatches"] += d["mismatches"]
                    t["max_abs_diff"] = max(t["max_abs_diff"], d["max_abs_diff"])
        ro = {"engine~reference": compare_readouts(readout_of(eng.get("pipeline")), readout_of(ref and ref.get("pipeline")))}
        if sp is not None:   # the spec reference runs the 12 settings and PPR 12 superflex
            ro["engine~spec"] = compare_readouts(readout_of(eng.get("pipeline")), sp.get("bench_share_readout"))
        cell["readout"] = ro
        for pair, d in ro.items():
            t = totals.setdefault(f"readout {pair}", {"mismatches": 0, "max_abs_diff": 0.0})
            t["mismatches"] += d["mismatches"]
            t["max_abs_diff"] = max(t["max_abs_diff"], d["max_abs_diff"] or 0.0)
        report["settings"][sid] = cell
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
    bad = 0
    for pair, t in totals.items():
        print(f"{pair}: {t.get('compared', '-')} compared, {t['mismatches']} disagreements, "
              f"max abs diff {t['max_abs_diff']:.6f}")
        bad += t["mismatches"]
    print(f"wrote {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
