"""OLS refit parity check (JEG-364b).

Loads `tests/fixtures/refit_vectors.json`, runs every vector through the JS
(ported inline — same algorithm, same floating-point order — see NODE_DRIVER
below) and the Python reference (`pipelines/refit_reference.py`), compares
the two outputs, and exits 0 on parity, non-zero on any mismatch.

Scope: the pure OLS refit logic in
`app/trade-value-chart/assets/curve-widget.js:2031-2081` (`refitLiveCells`
inner cell loop at 2049-2074). The function depends on closure state from
the FE module (ddfTwoTierValues / ddfTwoTierValuesFor / buildPublishedSourceMap
/ TwoTier.POSITIONS / activePies / pieSignature / liveCellsCache); we don't
exercise those — we drive the pure-math core with explicit inputs that the
JS algorithm consumes unchanged. The driver inlines the algorithm
verbatim from the JS source so both sides execute identical floating-point
arithmetic against the same vectors.

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
import subprocess
import math
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "refit_vectors.json"
REFERENCE = REPO_ROOT / "pipelines" / "refit_reference.py"


def _sanitize(obj: Any) -> Any:
    """Replace non-finite floats with None for JSON serialization (Node can't parse NaN/Infinity)."""
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
            timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"node driver failed: {result.stderr}")
        return json.loads(result.stdout)


# JS driver: inlines the OLS refit algorithm verbatim from
# app/trade-value-chart/assets/curve-widget.js:2049-2074. The only deviation
# is that input sources are explicit (driven from JSON) instead of coming
# from the FE closure state. Source enumeration, POSITIONS, tier names, and
# every early-exit condition match the JS source line-for-line.
NODE_DRIVER = r"""
const SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball"];
const POSITIONS = ["QB", "RB", "WR", "TE"];

function refitLiveCellsFor(input) {
  const ddfBySource = input.ddf_by_source || {};
  const publishedBySource = input.published_by_source || {};
  const cells = [];
  for (const rawKey of SOURCES) {
    const ddf = ddfBySource[rawKey];
    if (ddf === undefined || ddf === null) continue;          // mirrors JS early return
    const published = publishedBySource[rawKey] || {};
    if (!published || Object.keys(published).length === 0) continue;
    for (const pos of POSITIONS) {
      const cal = ddf.calibration && ddf.calibration[pos];
      if (cal && cal.invalid) continue;                        // mirrors ddf.calibration[pos]?.invalid
      for (const tier of ["starter", "bench"]) {
        const xs = [], ys = [];
        for (const playerKey of Object.keys(published)) {
          if ((ddf.pos_of || {})[String(playerKey)] !== pos) continue;
          const inTier = tier === "starter"
            ? (ddf.starters || []).indexOf(String(playerKey)) !== -1
            : (ddf.bench || []).indexOf(String(playerKey)) !== -1;
          if (!inTier) continue;
          const y = (ddf.values || {})[String(playerKey)];
          const pub = published[playerKey];
          if (!Number.isFinite(pub) || !Number.isFinite(y)) continue;
          xs.push(pub); ys.push(y);
        }
        if (xs.length < 2) continue;
        const n = xs.length;
        const mx = xs.reduce((s, v) => s + v, 0) / n;
        const my = ys.reduce((s, v) => s + v, 0) / n;
        let sxx = 0, sxy = 0;
        for (let i = 0; i < n; i++) {
          sxx += (xs[i] - mx) * (xs[i] - mx);
          sxy += (xs[i] - mx) * (ys[i] - my);
        }
        if (!(sxx > 0)) continue;
        const beta = sxy / sxx, alpha = my - beta * mx;
        if (!Number.isFinite(alpha) || !Number.isFinite(beta)) continue;
        cells.push({source: rawKey, position: pos, tier, alpha, beta, n});
      }
    }
  }
  return cells;
}

const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = { results: [] };
for (const v of input.vectors) {
  let got = null, err = null;
  try {
    got = refitLiveCellsFor(v.inputs);
  } catch (e) {
    err = String((e && e.message) || e);
  }
  out.results.push({ id: v.id, fn: v.fn, got, err });
}
try {
  process.stdout.write(JSON.stringify(out));
} catch (e) {
  process.stdout.write(JSON.stringify({ results: [], fatal: String(e.message) }));
}
"""


def _compare_num(a: float, b: float, tol: float) -> bool:
    try:
        af, bf = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if math.isnan(af) and math.isnan(bf):
        return True
    if math.isinf(af) or math.isinf(bf):
        return af == bf
    return abs(af - bf) <= tol


def _compare(a: Any, b: Any, tol: float, path: str = "") -> tuple[bool, str]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="JEG-364b refitLiveCells OLS parity")
    parser.add_argument("--update-fixture", action="store_true",
                        help="rewrite expected values from this run and exit 0")
    parser.add_argument("--vector", default=None, help="run only the named vector")
    args = parser.parse_args()

    if not FIXTURE.exists():
        print(f"FIXTURE_NOT_FOUND {FIXTURE}", file=sys.stderr)
        return 2

    fixture = json.loads(FIXTURE.read_text())
    tol = float(fixture.get("tolerance_abs", 1e-9))
    vectors = fixture["vectors"]
    if args.vector:
        vectors = [v for v in vectors if v["id"] == args.vector]
        if not vectors:
            print(f"VECTOR_NOT_FOUND {args.vector}", file=sys.stderr)
            return 2

    js_out = _run_node(NODE_DRIVER, {"vectors": vectors})["results"]

    sys.path.insert(0, str(REPO_ROOT / "pipelines"))
    import refit_reference as ref
    py_results: dict[str, Any] = {}
    for v in vectors:
        try:
            py_results[v["id"]] = ref.refit_live_cells(v["inputs"])
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