"""Run the clean-room pipeline on tests/fixtures/value_pipeline_worked_example.json
and compare every pinned leaf (VP-12: "reproduce it to 1e-6").

The fixture's `expected` block and `variant_bench_share_0_10` are walked
leaf by leaf; the pipeline's output may carry extra keys, but every key the
fixture pins must exist and match (numbers to TOL, everything else exactly).

Run: python3 pipelines/spec_reference/worked_example.py [fixture]
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "spec_reference"  # noqa: A001

from spec_reference import value_pipeline as vp  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"
TOL = 1e-6


def fixture_inputs(fx: dict) -> dict:
    pos_of = {int(k): v["pos"] for k, v in fx["players"].items()}
    names = {int(k): v.get("name") for k, v in fx["players"].items()}
    sources = {s: {"family": v["family"], "status": v.get("status"),
                   "values": {int(k): x for k, x in v["values"].items()}}
               for s, v in fx["inputs"].items()}
    included = [s for s, v in fx["inputs"].items() if v.get("status") == "included"]
    return {"pos_of": pos_of, "names": names, "sources": sources, "included": included}


def run_fixture(fx: dict, setting_change: dict | None = None) -> dict:
    inp = fixture_inputs(fx)
    s = copy.deepcopy(fx["setting"])
    s.update(setting_change or {})
    setting = vp.Setting.from_fixture(s)
    res = vp.run_week(setting, inp["pos_of"], inp["sources"], inp["included"], names=inp["names"])
    # expected.flex_contrast: the league flex by projected points against the
    # superseded per-source rule (each source's flex by its own natives, the
    # rule VP-2.2 f still uses in a degenerate week).
    contrast = {"by_mean_projected_points": {p: res["allocation"][p]["flex"] for p in vp.POSITIONS}}
    for s, src in inp["sources"].items():
        own = {k: float(v) for k, v in src["values"].items()}
        alloc = vp.allocate(setting, vp.score_order(own, inp["pos_of"]), own)
        contrast[f"{s}_by_own_values_superseded"] = {p: alloc[p]["flex"] for p in vp.POSITIONS}
    res["flex_contrast"] = contrast
    return res


def _get(actual, key):
    if isinstance(actual, dict):
        if key in actual:
            return True, actual[key]
        try:
            ik = int(key)
        except (TypeError, ValueError):
            return False, None
        if ik in actual:
            return True, actual[ik]
    return False, None


def walk(expected, actual, path: str, out: dict, tol: float = TOL) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            out["mismatches"].append({"path": path, "expected": "dict", "actual": repr(actual)[:80]})
            return
        for k, v in expected.items():
            ok, a = _get(actual, k)
            if not ok:
                out["mismatches"].append({"path": f"{path}.{k}", "expected": v if not isinstance(v, (dict, list)) else type(v).__name__, "actual": "<missing>"})
                continue
            walk(v, a, f"{path}.{k}", out, tol)
        return
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            out["mismatches"].append({"path": path, "expected": expected, "actual": actual})
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            walk(e, a, f"{path}[{i}]", out, tol)
        return
    out["compared"] += 1
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if expected != actual:
            out["mismatches"].append({"path": path, "expected": expected, "actual": actual})
        return
    if isinstance(actual, bool) or not isinstance(actual, (int, float)) or abs(float(actual) - float(expected)) > tol:
        out["mismatches"].append({"path": path, "expected": expected, "actual": actual})


def compare_fixture(fx: dict | None = None, tol: float = TOL) -> dict:
    fx = fx or json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = {"compared": 0, "mismatches": []}
    walk(fx["expected"], run_fixture(fx), "expected", out, tol)
    var = fx.get("variant_bench_share_0_10")
    if var:
        res = run_fixture(fx, var["setting_change"])
        actual = {"source_weights": {s: r["weights"] for s, r in res["sources"].items()},
                  "ddf_weights": res["ddf_weights"],
                  "rows_ddf_blended": {k: r["ddf_blended"]["value"] for k, r in res["rows"].items()}}
        walk({k: v for k, v in var.items() if k != "setting_change"}, actual,
             "variant_bench_share_0_10", out, tol)
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    fx = json.loads(Path(argv[0] if argv else FIXTURE).read_text(encoding="utf-8"))
    res = compare_fixture(fx)
    print(f"worked example: {res['compared']} leaves compared, {len(res['mismatches'])} mismatches")
    for m in res["mismatches"][:50]:
        print("  ", m)
    return 1 if res["mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
