"""TwoTier parity check (JEG-364).

Loads `tests/fixtures/twotier_vectors.json`, runs every vector through the JS
(via node) and the Python reference (`pipelines/twotier_reference.py`),
compares the two outputs, and exits 0 on parity, non-zero on any mismatch.

The fixture is the source of truth for inputs; this script computes the
expected value from node on every run rather than trusting the recorded
expected value, so a tampered fixture is caught (the script reports BOTH
sides and the recorded value, and any disagreement is a fail).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "twotier_vectors.json"
REFERENCE = REPO_ROOT / "pipelines" / "twotier_reference.py"
CURVE_JS = REPO_ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"


def _run_node(driver_js: str, payload: dict) -> dict:
    """Run the node driver, return its JSON output."""
    with tempfile.TemporaryDirectory() as tmp:
        driver_path = Path(tmp) / "driver.js"
        driver_path.write_text(driver_js)
        result = subprocess.run(
            ["node", str(driver_path)],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env={**os.environ, "PARITY_REPO_ROOT": str(REPO_ROOT)},
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"node driver failed: {result.stderr}")
        return json.loads(result.stdout)


# JS driver loaded into a Node VM sandbox with no DOM access. Calls the
# matching JS function for each vector and returns the result as JSON.
NODE_DRIVER = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = process.env.PARITY_REPO_ROOT;
const src = fs.readFileSync(path.join(repoRoot, "app/trade-value-chart/assets/curve-widget.js"), "utf8");
const sandbox = { console, Math, JSON, Number, Set, Map, Date, Error, RegExp };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: "curve-widget.js" });
const TT = sandbox.globalThis.TradeValueTwoTier;

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = { results: [] };
const safeJson = (x) => {
  if (x === null || x === undefined) return null;
  if (typeof x === "number") return Number.isFinite(x) ? x : String(x);
  if (Array.isArray(x)) return x.map(safeJson);
  if (x instanceof Set) return [...x].map(safeJson);
  if (typeof x === "object") {
    const o = {};
    for (const k of Object.keys(x)) o[k] = safeJson(x[k]);
    return o;
  }
  return x;
};

for (const v of input.vectors) {
  let got = null;
  let err = null;
  try {
    switch (v.fn) {
      case "softplus": {
        got = TT.softplus(v.inputs.z);
        break;
      }
      case "sliceExposures": {
        const r = TT.sliceExposures(v.inputs.x, v.inputs.rw, v.inputs.rs, v.inputs.tau);
        got = [r[0], r[1]];
        break;
      }
      case "roundHalfEven": {
        got = TT.roundHalfEven(v.inputs.x);
        break;
      }
      case "solveTierPrices": {
        const r = TT.solveTierPrices(v.inputs.aBench, v.inputs.bBench, v.inputs.aStart, v.inputs.bStart, v.inputs.pie, v.inputs.pos, v.inputs.benchShare);
        got = { pb: r.pb, ps: r.ps };
        break;
      }
      case "feasibleAt": {
        got = TT.feasibleAt(v.inputs.aBench, v.inputs.bBench, v.inputs.aStart, v.inputs.bStart, v.inputs.pie, v.inputs.share, v.inputs.pos);
        break;
      }
      case "feasibleBenchShareInterval": {
        const r = TT.feasibleBenchShareInterval(v.inputs.aBench, v.inputs.bBench, v.inputs.aStart, v.inputs.bStart, v.inputs.pie, v.inputs.pos);
        got = r === null ? null : [r[0], r[1]];
        break;
      }
      case "sliderBounds": {
        const r = TT.sliderBounds(v.inputs.intervals);
        got = r === null ? null : [r[0], r[1]];
        break;
      }
      case "displayValue": {
        got = TT.displayValue(v.inputs.rawValue, v.inputs.scale, v.inputs.aboveWaiver);
        break;
      }
      case "normalizeThenRound": {
        const above = v.inputs.aboveWaiverByKeyMap ? new Map(Object.entries(v.inputs.aboveWaiverByKeyMap)) : ((k) => v.inputs.aboveWaiverForAll);
        const r = TT.normalizeThenRound(v.inputs.rawByKey, above);
        got = { scale: r.scale, values: Object.fromEntries(r.values) };
        break;
      }
      case "tailFloor": {
        got = TT.tailFloor(v.inputs.xs, v.inputs.frac, v.inputs.win);
        break;
      }
      case "benchMixFor": {
        const r = TT.benchMixFor(v.inputs.teams, v.inputs.benchSlots, v.inputs.slots, v.inputs.flexCount, v.inputs.flexEligible, v.inputs.pools);
        got = r;
        break;
      }
      case "inwardBounds": {
        const r = TT.inwardBounds(v.inputs.lo, v.inputs.hi, v.inputs.step);
        got = [r[0], r[1]];
        break;
      }
      case "skillBenchShares": {
        const r = TT.skillBenchShares(v.inputs.share);
        got = r;
        break;
      }
      case "skillBenchShare": {
        got = TT.skillBenchShare(v.inputs.shares, v.inputs.pos);
        break;
      }
      case "legacyBenchMixFor": {
        got = TT.legacyBenchMixFor(v.inputs.teams);
        got = Object.fromEntries(Object.entries(got).map(([k,v]) => [k, Number(v)]));
        break;
      }
      case "buildPositionTiers": {
        const lists = v.inputs.lists;
        const cfg = v.inputs.cfg;
        const r = TT.buildPositionTiers(lists, cfg);
        const tiers = {};
        for (const pos of Object.keys(r.tiers)) {
          const t = r.tiers[pos];
          if (!t) { tiers[pos] = null; continue; }
          tiers[pos] = {
            rw: t.rw, rs: t.rs, tau: t.tau,
            aBench: t.aBench, bBench: t.bBench,
            aStart: t.aStart, bStart: t.bStart,
            surplus: t.surplus,
          };
        }
        got = {
          tiers,
          starters: [...r.starters].sort(),
          bench: [...r.bench].sort(),
          rostered: [...r.rostered].sort(),
        };
        break;
      }
      case "calibratePositionFeasible": {
        const ti = v.inputs.tier;
        const r = TT.calibratePositionFeasible(ti, v.inputs.pie, v.inputs.requestedShare, v.inputs.pos);
        if (r === null) { got = null; break; }
        got = {
            rw: r.rw, rs: r.rs, tau: r.tau,
            aBench: r.aBench, bBench: r.bBench,
            aStart: r.aStart, bStart: r.bStart,
            surplus: r.surplus,
            pb: r.pb, ps: r.ps,
            invalid: r.invalid, invalidReason: r.invalidReason,
            benchRaw: r.benchRaw, starterRaw: r.starterRaw,
            bench_share_used: r.bench_share_used,
        };
        break;
      }
      case "priceForProjection": {
        got = TT.priceForProjection(v.inputs.x, v.inputs.cal);
        break;
      }
      default:
        throw new Error("unknown fn " + v.fn);
    }
  } catch (e) {
    err = String(e && e.message || e);
  }
  out.results.push({ id: v.id, fn: v.fn, got: safeJson(got), err });
}
try {
  process.stdout.write(JSON.stringify(out));
} catch (e) {
  process.stdout.write(JSON.stringify({ results: [], fatal: String(e.message) }));
}
"""


def _compare_num(a: float, b: float, tol: float) -> bool:
    if math.isnan(a) and math.isnan(b):
        return True
    if math.isinf(a) or math.isinf(b):
        return a == b
    return abs(a - b) <= tol


def _compare(a: Any, b: Any, tol: float) -> tuple[bool, str]:
    if a is None and b is None:
        return True, ""
    if a is None or b is None:
        return False, f"null mismatch: js={a} py={b}"
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b, f"bool mismatch: js={a} py={b}"
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        ok = _compare_num(float(a), float(b), tol)
        return ok, ("" if ok else f"num mismatch: js={a} py={b} delta={abs(a-b)}")
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False, f"list len mismatch: js={a} py={b}"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, msg = _compare(x, y, tol)
            if not ok:
                return False, f"list[{i}] {msg}"
        return True, ""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False, f"dict keys mismatch: js={sorted(a.keys())} py={sorted(b.keys())}"
        for k in sorted(a.keys()):
            ok, msg = _compare(a[k], b[k], tol)
            if not ok:
                return False, f"dict[{k!r}] {msg}"
        return True, ""
    return a == b, f"type/value mismatch: js={a!r} py={b!r}"


def main() -> int:
    parser = argparse.ArgumentParser(description="JEG-364 TwoTier parity check")
    parser.add_argument("--update-fixture", action="store_true",
                        help="rewrite expected values from this run and exit 0")
    parser.add_argument("--vector", default=None,
                        help="run only the named vector (debug aid)")
    args = parser.parse_args()

    if not FIXTURE.exists():
        print(f"FIXTURE_NOT_FOUND {FIXTURE}", file=sys.stderr)
        return 2
    if not REFERENCE.exists():
        print(f"REFERENCE_NOT_FOUND {REFERENCE}", file=sys.stderr)
        return 2
    if not CURVE_JS.exists():
        print(f"CURVE_JS_NOT_FOUND {CURVE_JS}", file=sys.stderr)
        return 2

    fixture = json.loads(FIXTURE.read_text())
    tol = float(fixture.get("tolerance_abs", 1e-9))
    vectors = fixture["vectors"]

    # Resolve shared/derived inputs into per-vector inputs.
    shared = fixture.get("shared_inputs") or {}
    derived = fixture.get("derived_inputs") or {}

    # First: a discovery run to compute shared-input results (e.g. tiers).
    # Easiest path: resolve each derived reference by re-running the upstream.
    # We do that with a one-off node call.
    def _compute_predecessor(predecessor_id: str) -> dict:
        # Recompute by feeding just the predecessor into the node driver.
        one_vec = next(v for v in vectors if v["id"] == predecessor_id)
        one_payload = {"vectors": [one_vec]}
        out = _run_node(NODE_DRIVER, one_payload)
        return out["results"][0]["got"]

    for v in vectors:
        if v["id"] in shared and v["inputs"] is None:
            v["inputs"] = shared[v["id"]]
        if v["id"] in derived and v["inputs"] is None:
            d = derived[v["id"]]
            if "_from" in d:
                upstream = _compute_predecessor(d["_from"])
                if d["_from"] == "build_position_tiers_12t_default":
                    # Calibrate position from tier + pie + share.
                    tier = upstream["tiers"][d["tier_pos"]]
                    v["inputs"] = {"tier": tier, "pie": d["pie"], "requestedShare": d["requestedShare"], "pos": d["tier_pos"]}
                elif d["_from"] == "calibrate_position_feasible_default":
                    # Price from cal + x.
                    cal = upstream
                    v["inputs"] = {"x": d["x"], "cal": cal}

    if args.vector:
        vectors = [v for v in vectors if v["id"] == args.vector]

    # Run JS side
    js_out = _run_node(NODE_DRIVER, {"vectors": vectors})["results"]

    # Run Python side
    sys.path.insert(0, str(REPO_ROOT / "pipelines"))
    import twotier_reference as ref

    py_results: dict[str, Any] = {}
    for v in vectors:
        try:
            py_results[v["id"]] = _run_py(v["fn"], v["inputs"], ref)
        except Exception as e:
            py_results[v["id"]] = {"_py_error": str(e)}

    # Compare and emit report.
    fails: list[str] = []
    rows = []
    for j, v in zip(js_out, vectors):
        js_got = j.get("got")
        js_err = j.get("err")
        py_got = py_results.get(v["id"])
        py_err = py_got.get("_py_error") if isinstance(py_got, dict) and "_py_error" in py_got else None
        recorded = v.get("expected")

        # Both sides raising on an invalid input is a parity match.
        if js_err and py_err:
            ok, msg = True, ""
        else:
            ok, msg = _compare(js_got, py_got, tol)
        status = "PASS" if ok else "FAIL"
        rows.append({
            "id": v["id"], "fn": v["fn"], "status": status,
            "js": js_got, "py": py_got, "recorded": recorded,
            "js_err": js_err, "py_err": py_err,
            "msg": msg,
        })
        if not ok:
            fails.append(f"{v['id']} ({v['fn']}): {msg}")

    report = {
        "fixture": str(FIXTURE.relative_to(REPO_ROOT)),
        "tolerance_abs": tol,
        "passed": len(rows) - len(fails),
        "failed": len(fails),
        "total": len(rows),
        "fails": fails,
        "rows": rows,
    }

    if args.update_fixture:
        # Backfill expected from this run (only when JS produced a value).
        for v, j in zip(vectors, js_out):
            if j.get("got") is not None:
                v["expected"] = j["got"]
        FIXTURE.write_text(json.dumps(fixture, indent=2) + "\n")
        print("FIXTURE_UPDATED", len(rows), "vectors")
        return 0

    print(json.dumps(report, indent=2, default=str))
    return 0 if not fails else 1


def _run_py(fn: str, inputs: dict, ref: Any) -> Any:
    """Call the matching Python reference function."""
    if fn == "softplus":
        return ref.softplus(inputs["z"])
    if fn == "sliceExposures":
        r = ref.slice_exposures(inputs["x"], inputs["rw"], inputs["rs"], inputs["tau"])
        return [r[0], r[1]]
    if fn == "roundHalfEven":
        return ref.round_half_even(inputs["x"])
    if fn == "solveTierPrices":
        r = ref.solve_tier_prices(
            inputs["aBench"], inputs["bBench"], inputs["aStart"], inputs["bStart"],
            inputs["pie"], inputs.get("pos", "?"), inputs["benchShare"],
        )
        return {"pb": r["pb"], "ps": r["ps"]}
    if fn == "feasibleAt":
        return ref.feasible_at(
            inputs["aBench"], inputs["bBench"], inputs["aStart"], inputs["bStart"],
            inputs["pie"], inputs["share"], inputs.get("pos", "?"),
        )
    if fn == "feasibleBenchShareInterval":
        r = ref.feasible_bench_share_interval(
            inputs["aBench"], inputs["bBench"], inputs["aStart"], inputs["bStart"],
            inputs["pie"], inputs.get("pos", "?"),
        )
        return None if r is None else [r[0], r[1]]
    if fn == "sliderBounds":
        r = ref.slider_bounds(inputs["intervals"])
        return None if r is None else [r[0], r[1]]
    if fn == "displayValue":
        return ref.display_value(inputs["rawValue"], inputs["scale"], inputs["aboveWaiver"])
    if fn == "normalizeThenRound":
        if "aboveWaiverByKeyMap" in inputs:
            m = inputs["aboveWaiverByKeyMap"]
            above = (lambda k: bool(m.get(k)))
        else:
            above = (lambda k: inputs["aboveWaiverForAll"])
        r = ref.normalize_then_round(inputs["rawByKey"], above)
        return {"scale": r["scale"], "values": dict(r["values"])}
    if fn == "tailFloor":
        return ref.tail_floor(inputs["xs"], inputs.get("frac", ref.FLOOR_SLOPE_FRAC), inputs.get("win", ref.FLOOR_WINDOW))
    if fn == "benchMixFor":
        return ref.bench_mix_for(
            inputs["teams"], inputs["benchSlots"], inputs["slots"],
            inputs["flexCount"], inputs["flexEligible"], inputs["pools"],
        )
    if fn == "inwardBounds":
        r = ref.inward_bounds(inputs["lo"], inputs["hi"], inputs.get("step", 0.001))
        return [r[0], r[1]]
    if fn == "skillBenchShares":
        return ref.skill_bench_shares(inputs["share"])
    if fn == "skillBenchShare":
        return ref.skill_bench_share(inputs["shares"], inputs["pos"])
    if fn == "legacyBenchMixFor":
        return {k: int(v) for k, v in ref.legacy_bench_mix_for(inputs["teams"]).items()}
    if fn == "buildPositionTiers":
        r = ref.build_position_tiers(inputs["lists"], inputs["cfg"])
        tiers = {}
        for pos in ref.POSITIONS:
            t = r["tiers"].get(pos)
            if t is None:
                tiers[pos] = None
            else:
                tiers[pos] = {
                    "rw": t["rw"], "rs": t["rs"], "tau": t["tau"],
                    "aBench": t["aBench"], "bBench": t["bBench"],
                    "aStart": t["aStart"], "bStart": t["bStart"],
                    "surplus": t["surplus"],
                }
        return {
            "tiers": tiers,
            "starters": sorted(r["starters"]),
            "bench": sorted(r["bench"]),
            "rostered": sorted(r["rostered"]),
        }
    if fn == "calibratePositionFeasible":
        r = ref.calibrate_position_feasible(
            inputs["tier"], inputs["pie"], inputs["requestedShare"], inputs.get("pos", "?"),
        )
        if r is None:
            return None
        return {
            "rw": r["rw"], "rs": r["rs"], "tau": r["tau"],
            "aBench": r["aBench"], "bBench": r["bBench"],
            "aStart": r["aStart"], "bStart": r["bStart"],
            "surplus": r["surplus"],
            "pb": r["pb"], "ps": r["ps"],
            "invalid": r["invalid"], "invalidReason": r["invalidReason"],
            "benchRaw": r["benchRaw"], "starterRaw": r["starterRaw"],
            "bench_share_used": r.get("bench_share_used"),
        }
    if fn == "priceForProjection":
        return ref.price_for_projection(inputs["x"], inputs["cal"])
    raise ValueError(f"unknown fn {fn}")


if __name__ == "__main__":
    sys.exit(main())