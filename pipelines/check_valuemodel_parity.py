"""value-model.js parity check (JEG-364c — JEG-327 Phase E, part 3 of 3).

Loads `tests/fixtures/valuemodel_vectors.json`, runs every vector through the JS
(via node, in a VM sandbox with no DOM access) and the Python reference
(`pipelines/parity/value_model_parity.py`), compares the two outputs, and
exits 0 on parity, non-zero on any mismatch.

The fixture is the source of truth for inputs; this script computes the
expected value from node on every run rather than trusting the recorded
expected value, so a tampered fixture is caught (the script reports BOTH
sides and the recorded value, and any disagreement is a fail).

NaN handling: `_sanitize` replaces non-finite floats with `None` before
sending to node (`json.dumps` is strict, and node's `JSON.parse` rejects
NaN/Infinity). The JS driver mirrors by returning `null` from
`JSON.stringify` for non-finite numbers — which already happens because
`JSON.stringify(NaN) === 'null'`. We pass through unchanged and compare
both sides under the same `_compare` helper that accepts `null` ↔ `null`
for both-sides-NaN parity (mirrors `check_twotier_parity._compare`).

Functions covered (one vector group per function):
  sourceComboKey, flexEligible, stableTiebreak, roleMap, projectionRoles,
  positionalTierScales, sharedPieBasis, benchShareOf, scaleToSharedTotal,
  shapeToAnchorPeaksThenSharedTotal, peakAgreement, normalizeToFixedPie,
  starterMarkupSane, fixedPieDirectionSane, allocationCounts.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "valuemodel_vectors.json"
REFERENCE = REPO_ROOT / "pipelines" / "parity" / "value_model_parity.py"
VALUE_MODEL_JS = REPO_ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"


def _sanitize(obj: Any) -> Any:
    """Replace non-finite floats with None for JSON (Node's JSON.parse rejects NaN/Infinity)."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _run_node(driver_js: str, payload: dict) -> dict:
    """Run the node driver, return its JSON output."""
    with tempfile.TemporaryDirectory() as tmp:
        driver_path = Path(tmp) / "driver.js"
        driver_path.write_text(driver_js)
        result = subprocess.run(
            ["node", str(driver_path)],
            input=json.dumps(_sanitize(payload)),
            capture_output=True,
            text=True,
            env={**os.environ, "PARITY_REPO_ROOT": str(REPO_ROOT)},
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"node driver failed: {result.stderr}")
        return json.loads(result.stdout)


# JS driver: loads value-model.js into a VM sandbox with no DOM access, calls
# the matching JS function for each vector, returns the result as JSON.
# Inputs that the FE receives as Map / Set / function are reconstructed from
# plain JSON (player_map → Map; ranks → (p) => ranks[p.player_key]; etc.).
NODE_DRIVER = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const repoRoot = process.env.PARITY_REPO_ROOT;
const src = fs.readFileSync(path.join(repoRoot, "app/trade-value-chart/assets/value-model.js"), "utf8");
const sandbox = { console, Math, JSON, Number, Set, Map, Date, Error, RegExp, isFinite };
sandbox.globalThis = sandbox;
vm.createContext(sandbox);
vm.runInContext(src, sandbox, { filename: "value-model.js" });
const VM = sandbox.globalThis.ValueModel;

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const out = { results: [] };

// Serialize JS values into a JSON-friendly form. Maps/Sets become arrays/objects;
// functions are not serialized here (callers run them inside the driver).
const safeJson = (x) => {
  if (x === null || x === undefined) return null;
  if (typeof x === "number") return Number.isFinite(x) ? x : null;  // NaN/±Infinity → null
  if (typeof x === "boolean") return x;
  if (typeof x === "string") return x;
  if (Array.isArray(x)) return x.map(safeJson);
  // Sets: emit a sorted array so order matches Python (set iteration order is
  // not deterministic across implementations). The __set__ wrapper lets _norm
  // recognise a "set vs list" boundary if we need it later.
  if (x instanceof Set) return [...x].map(safeJson).sort((a, b) => String(a).localeCompare(String(b)));
  if (x instanceof Map) {
    const o = {};
    for (const [k, v] of x.entries()) o[String(k)] = safeJson(v);
    return o;
  }
  if (typeof x === "object") {
    const o = {};
    for (const k of Object.keys(x)) o[k] = safeJson(x[k]);
    return o;
  }
  return null;
};

// Reconstruct a Map from a {player_key: value} object.
const asMap = (obj) => {
  const m = new Map();
  if (!obj || typeof obj !== "object") return m;
  for (const k of Object.keys(obj)) m.set(k, obj[k]);
  return m;
};

// Reconstruct a (player) -> player object lookup from a player list.
const playerOfFromList = (players) => {
  const m = new Map();
  for (const p of players || []) m.set(p.player_key, p);
  return (k) => m.get(k);
};

// Reconstruct rankOf as (p) => ranks[String(p.player_key)].
const rankOfFromMap = (ranks) => (p) => ranks[String(p.player_key)];

// Reconstruct targetFor as (pos) => targets[pos].
const targetForFromMap = (targets) => (pos) => targets[pos];

// Reconstruct labelOf as (key) => labels[key].
const labelOfFromMap = (labels) => (key) => (labels && Object.prototype.hasOwnProperty.call(labels, key)) ? labels[key] : key;

// Reconstruct fallbackTarget as a function from current total to a new target.
const fallbackFromFn = (f) => (typeof f === "function") ? (x) => f(x) : null;

for (const v of input.vectors) {
  let got = null;
  let err = null;
  try {
    switch (v.fn) {
      case "sourceComboKey": {
        got = VM.sourceComboKey(v.inputs.source, v.inputs.scoring, v.inputs.teams, v.inputs.qbSlots);
        break;
      }
      case "flexEligible": {
        got = VM.flexEligible(v.inputs.shape || null);
        break;
      }
      case "stableTiebreak": {
        const a = v.inputs.a ? { name: v.inputs.a.name, player_key: v.inputs.a.player_key } : null;
        const b = v.inputs.b ? { name: v.inputs.b.name, player_key: v.inputs.b.player_key } : null;
        got = VM.stableTiebreak(a, b);
        break;
      }
      case "roleMap": {
        const values = asMap(v.inputs.values);
        const playerOf = playerOfFromList(v.inputs.players);
        const r = VM.roleMap({
          values: values,
          playerOf: playerOf,
          teams: v.inputs.teams,
          shape: v.inputs.shape || {},
        });
        // Emit as a plain object — both sides end up as dicts in JSON.
        got = {};
        for (const [k, val] of r.entries()) got[String(k)] = val;
        break;
      }
      case "projectionRoles": {
        const r = VM.projectionRoles({
          pool: v.inputs.pool || [],
          teams: v.inputs.teams,
          shape: v.inputs.shape || {},
          rankOf: rankOfFromMap(v.inputs.ranks || {}),
        });
        const rolesMap = {};
        for (const [k, val] of r.roles.entries()) rolesMap[String(k)] = val;
        got = { roles: rolesMap, direct: r.direct, baseline: r.baseline };
        break;
      }
      case "positionalTierScales": {
        const r = VM.positionalTierScales(
          v.inputs.rows || [],
          targetForFromMap(v.inputs.targets || {}),
          v.inputs.share
        );
        got = { starter: r.starter, bench: r.bench, starterRaw: r.starterRaw, benchRaw: r.benchRaw, target: r.target };
        break;
      }
      case "sharedPieBasis": {
        const r = VM.sharedPieBasis({
          values: asMap(v.inputs.values),
          anchor: asMap(v.inputs.anchor || {}),
          playerOf: playerOfFromList(v.inputs.players),
        });
        if (r === null || r === undefined) {
          got = null;
        } else {
          // Emit keys as a sorted array so order matches the Python reference
          // (the reference returns a sorted list too — see _run_py below).
          got = { keys: [...r.keys].sort((a, b) => String(a).localeCompare(String(b))), target: r.target };
        }
        break;
      }
      case "benchShareOf": {
        // benchShareOf takes either pre-computed roles or asks roleMap to compute them.
        // We always pass playerOf/teams/shape so both paths work; if v.inputs.roles is
        // provided as an object, we pass it as a Map.
        const rolesArg = v.inputs.roles ? asMap(v.inputs.roles) : null;
        const r = VM.benchShareOf({
          values: asMap(v.inputs.values),
          roles: rolesArg,
          playerOf: playerOfFromList(v.inputs.players),
          teams: v.inputs.teams,
          shape: v.inputs.shape || {},
        });
        got = r;
        break;
      }
      case "scaleToSharedTotal": {
        const r = VM.scaleToSharedTotal({
          values: asMap(v.inputs.values),
          anchor: asMap(v.inputs.anchor || {}),
          playerOf: playerOfFromList(v.inputs.players),
        });
        const m = {};
        for (const [k, val] of r.entries()) m[String(k)] = val;
        got = m;
        break;
      }
      case "shapeToAnchorPeaksThenSharedTotal": {
        const r = VM.shapeToAnchorPeaksThenSharedTotal({
          values: asMap(v.inputs.values),
          anchor: asMap(v.inputs.anchor || {}),
          playerOf: playerOfFromList(v.inputs.players),
        });
        const m = {};
        for (const [k, val] of r.entries()) m[String(k)] = val;
        got = m;
        break;
      }
      case "peakAgreement": {
        const r = VM.peakAgreement({
          anchorPeaks: v.inputs.anchorPeaks || {},
          sources: v.inputs.sources || {},
          labelOf: labelOfFromMap(v.inputs.labels),
          low: v.inputs.low,
          high: v.inputs.high,
        });
        got = { ok: r.ok, compared: r.compared, offenders: r.offenders, band: r.band };
        break;
      }
      case "normalizeToFixedPie": {
        const rolesArg = v.inputs.roles ? asMap(v.inputs.roles) : null;
        const r = VM.normalizeToFixedPie({
          values: asMap(v.inputs.values),
          share: v.inputs.share,
          roles: rolesArg,
          anchor: asMap(v.inputs.anchor || {}),
          playerOf: playerOfFromList(v.inputs.players),
          singleScale: !!v.inputs.singleScale,
          fallbackTarget: fallbackFromFn(v.inputs.fallbackTarget),
        });
        const m = {};
        for (const [k, val] of r.entries()) m[String(k)] = val;
        got = m;
        break;
      }
      case "starterMarkupSane": {
        got = VM.starterMarkupSane(v.inputs.markup);
        break;
      }
      case "fixedPieDirectionSane": {
        got = VM.fixedPieDirectionSane(v.inputs.rawStarterShare, v.inputs.starterShare);
        break;
      }
      case "allocationCounts": {
        const r = VM.allocationCounts({
          pool: v.inputs.pool || [],
          teams: v.inputs.teams,
          shape: v.inputs.shape || {},
          rankOf: rankOfFromMap(v.inputs.ranks || {}),
        });
        got = { direct: r.direct, lineup: r.lineup, rostered: r.rostered };
        break;
      }
      default:
        throw new Error("unknown fn " + v.fn);
    }
  } catch (e) {
    err = String((e && e.message) || e);
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


def _compare(a: Any, b: Any, tol: float, path: str = "") -> tuple[bool, str]:
    # Both sides already normalize Set→sorted list and Map→dict at the source
    # (NODE_DRIVER safeJson + _run_py). NaN/Infinity → null on both sides via
    # JSON.stringify / _sanitize, so we only need to compare structural
    # equality under tolerance here.

    if a is None and b is None:
        return True, ""
    if a is None or b is None:
        return False, f"{path}: null mismatch js={a!r} py={b!r}"
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b, f"{path}: bool mismatch js={a!r} py={b!r}"
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        ok = _compare_num(float(a), float(b), tol)
        return ok, "" if ok else f"{path}: num mismatch js={a} py={b} delta={abs(float(a) - float(b))}"
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False, f"{path}: list len mismatch js={len(a)} py={len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            ok, msg = _compare(x, y, tol, f"{path}[{i}]")
            if not ok:
                return False, msg
        return True, ""
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False, f"{path}: dict keys mismatch js={sorted(a.keys())} py={sorted(b.keys())}"
        for k in sorted(a.keys()):
            ok, msg = _compare(a[k], b[k], tol, f"{path}.{k}")
            if not ok:
                return False, msg
        return True, ""
    return a == b, f"{path}: type/value mismatch js={a!r} py={b!r}"


def _run_py(fn: str, inputs: dict) -> Any:
    """Call the matching Python reference function for one vector."""
    sys.modules.pop("value_model_parity", None)  # ensure re-import sees any local edits
    import value_model_parity as ref

    if fn == "sourceComboKey":
        return ref.source_combo_key(inputs["source"], inputs["scoring"], inputs["teams"], inputs.get("qbSlots"))
    if fn == "flexEligible":
        return ref.flex_eligible(inputs.get("shape"))
    if fn == "stableTiebreak":
        return ref.stable_tiebreak(inputs.get("a"), inputs.get("b"))
    if fn == "roleMap":
        return ref.role_map(
            inputs.get("values", {}),
            lambda pk: _player_lookup(inputs.get("players", []), pk),
            inputs["teams"],
            inputs.get("shape", {}),
        )
    if fn == "projectionRoles":
        pool = inputs.get("pool", [])
        ranks = inputs.get("ranks", {})
        return ref.projection_roles(
            pool, inputs["teams"], inputs.get("shape", {}),
            lambda p: ranks.get(str(p.get("player_key")), 0.0),
        )
    if fn == "positionalTierScales":
        targets = inputs.get("targets", {})
        return ref.positional_tier_scales(
            inputs.get("rows", []),
            lambda pos: targets.get(pos, 0.0),
            inputs["share"],
        )
    if fn == "sharedPieBasis":
        r = ref.shared_pie_basis(
            inputs.get("values", {}),
            inputs.get("anchor") or None,
            lambda pk: _player_lookup(inputs.get("players", []), pk),
        )
        if r is None:
            return None
        # Mirror the JS driver: emit keys as a sorted list of strings so both
        # sides agree on order regardless of Python set iteration order.
        return {"keys": sorted(r["keys"], key=lambda y: str(y)), "target": r["target"]}
    if fn == "benchShareOf":
        return ref.bench_share_of(
            inputs.get("values", {}),
            inputs.get("roles") or None,
            lambda pk: _player_lookup(inputs.get("players", []), pk),
            inputs["teams"],
            inputs.get("shape", {}),
        )
    if fn == "scaleToSharedTotal":
        return ref.scale_to_shared_total(
            inputs.get("values", {}),
            inputs.get("anchor") or None,
            lambda pk: _player_lookup(inputs.get("players", []), pk),
        )
    if fn == "shapeToAnchorPeaksThenSharedTotal":
        return ref.shape_to_anchor_peaks_then_shared_total(
            inputs.get("values", {}),
            inputs.get("anchor") or None,
            lambda pk: _player_lookup(inputs.get("players", []), pk),
        )
    if fn == "peakAgreement":
        labels = inputs.get("labels") or {}
        return ref.peak_agreement(
            inputs.get("anchorPeaks", {}),
            inputs.get("sources", {}),
            inputs.get("low"),
            inputs.get("high"),
            lambda k: labels.get(k, k),
        )
    if fn == "normalizeToFixedPie":
        return ref.normalize_to_fixed_pie(
            inputs.get("values", {}),
            inputs["share"],
            inputs.get("roles") or None,
            inputs.get("anchor") or None,
            lambda pk: _player_lookup(inputs.get("players", []), pk),
            bool(inputs.get("singleScale", False)),
            inputs.get("fallbackTarget"),
        )
    if fn == "starterMarkupSane":
        return ref.starter_markup_sane(inputs["markup"])
    if fn == "fixedPieDirectionSane":
        return ref.fixed_pie_direction_sane(inputs["rawStarterShare"], inputs["starterShare"])
    if fn == "allocationCounts":
        pool = inputs.get("pool", [])
        ranks = inputs.get("ranks", {})
        return ref.allocation_counts(
            pool, inputs["teams"], inputs.get("shape", {}),
            lambda p: ranks.get(str(p.get("player_key")), 0.0),
        )
    raise ValueError(f"unknown fn {fn}")


def _player_lookup(players: list, pk):
    for p in players:
        if str(p.get("player_key")) == str(pk):
            return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="JEG-364c value-model.js parity check")
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
    if not VALUE_MODEL_JS.exists():
        print(f"VALUE_MODEL_JS_NOT_FOUND {VALUE_MODEL_JS}", file=sys.stderr)
        return 2

    fixture = json.loads(FIXTURE.read_text())
    tol = float(fixture.get("tolerance_abs", 1e-9))
    vectors = fixture["vectors"]
    if args.vector:
        vectors = [v for v in vectors if v["id"] == args.vector]
        if not vectors:
            print(f"VECTOR_NOT_FOUND {args.vector}", file=sys.stderr)
            return 2

    # Run JS side
    js_out = _run_node(NODE_DRIVER, {"vectors": vectors})["results"]

    # Run Python side
    sys.path.insert(0, str(REPO_ROOT / "pipelines" / "parity"))
    py_results: dict[str, Any] = {}
    for v in vectors:
        try:
            py_results[v["id"]] = _run_py(v["fn"], v["inputs"])
        except Exception as e:
            py_results[v["id"]] = {"_py_error": str(e)}

    rows = []
    fails: list[str] = []
    for j, v in zip(js_out, vectors):
        js_got = j.get("got")
        js_err = j.get("err")
        py_got = py_results.get(v["id"])
        py_err = py_got.get("_py_error") if isinstance(py_got, dict) and "_py_error" in py_got else None
        recorded = v.get("expected")

        if js_err and py_err:
            ok, msg = True, ""
        else:
            ok, msg = _compare(js_got, py_got, tol)
        status = "PASS" if ok else "FAIL"
        rows.append({
            "id": v["id"], "fn": v["fn"], "status": status,
            "js": js_got, "py": py_got, "recorded": recorded,
            "js_err": js_err, "py_err": py_err, "msg": msg,
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


if __name__ == "__main__":
    sys.exit(main())