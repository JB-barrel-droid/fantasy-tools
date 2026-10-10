"""Shared checker for the worked example's expected-starts variants (JEG-536).

tests/fixtures/value_pipeline_worked_example.json carries
`variant_expected_starts` and `variant_expected_starts_override`
(tools/worked_example_expected_starts.py). Each implementation's result is
mapped to the variant's vocabulary by `view()` and walked leaf by leaf by
`diff()`: every pinned number to 1e-6, every flag exactly. Used by the engine,
Python reference and spec reference tests.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"
TOL = 1e-6
VARIANTS = ("variant_expected_starts", "variant_expected_starts_override")


def load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _get(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return True, obj[key]
        try:
            ik = int(key)
        except (TypeError, ValueError):
            return False, None
        if ik in obj:
            return True, obj[ik]
    return False, None


def diff(expected, actual, path: str = "", out: list | None = None) -> list:
    out = [] if out is None else out
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            out.append(f"{path}: expected object, got {actual!r}"[:300])
            return out
        for k, v in expected.items():
            ok, a = _get(actual, k)
            if not ok:
                out.append(f"{path}.{k}: missing")
                continue
            diff(v, a, f"{path}.{k}", out)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            out.append(f"{path}: expected {expected!r}, got {actual!r}"[:300])
            return out
        for i, (e, a) in enumerate(zip(expected, actual)):
            diff(e, a, f"{path}[{i}]", out)
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if expected != actual:
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif isinstance(actual, bool) or not isinstance(actual, (int, float)) or abs(expected - actual) > TOL:
        out.append(f"{path}: expected {expected!r}, got {actual!r}")
    return out


def count_leaves(obj) -> int:
    if isinstance(obj, dict):
        return sum(count_leaves(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(count_leaves(v) for v in obj)
    return 1


def _ddf_value(row: dict):
    """A row's blended DDF Value in any implementation's shape."""
    if "ddf" in row:
        return row["ddf"]["blended"]["value"]
    d = row.get("ddf_blended")
    return d["value"] if isinstance(d, dict) else d


def view(res: dict) -> dict:
    """Map a result (driver JSON, value_reference or spec_reference) to the
    variants' vocabulary. Missing pieces stay missing so diff() reports them."""
    cs = res.get("chart_sigma")
    if isinstance(cs, dict):
        cs = {p: (v["sigma_rel"] if isinstance(v, dict) else v) for p, v in cs.items()}
    readout = res.get("bench_share_readout")
    out = {"chart_sigma": cs, "bench_share_applied": res.get("bench_share_applied"),
           "ddf_weights": res.get("ddf_weights"), "group_budgets": res.get("group_budgets"),
           "bench_share_readout": readout,
           "source_weights": {k: d.get("weights") for k, d in res["sources"].items()},
           "sources": res["sources"],
           "rows": {k: {"ddf_blended": _ddf_value(r), "lineup_share": r.get("lineup_share"),
                        "start_worthy": r.get("start_worthy")} for k, r in res["rows"].items()},
           "rows_ddf_blended": {k: _ddf_value(r) for k, r in res["rows"].items()}}
    return out


def variant_problems(doc: dict, name: str, res: dict) -> list:
    return diff(doc[name]["expected"], view(res), name)
