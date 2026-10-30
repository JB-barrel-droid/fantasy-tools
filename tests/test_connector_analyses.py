"""JEG-1029: reference parity for the connector's analyses (risers_fallers, compare_trade by_source,
audit_values), offline: node and the built dist/, no browser, no network.

Two halves, both against pipelines/value_reference.py (written from the methodology, not from the
engine):

1. get-values' new blocks (supabase/functions/get-values/analysis.ts, run by the parity runner on the
   function's own pipeline.ts): include=series is the page's Player values rows (the reference's
   rows("indexed") with the three DDF Value versions), include=prior is the VP-8 prior week (the
   reference's prior_result(): the same league, included set and pie on Week N-1's inputs), and
   include=audit's diagnostics are the reference's diagnostics() (pie, included set, each source's
   position counts). To 1e-6.
2. The tools against the page modules: tests/node/connector_analyses_driver.mjs runs the tools on the
   edge blocks and the page's own movers.js / trade.js on the reference's rows and prior week; the
   answers must be the same (risers, fallers, counts, disagreements, every compare row and verdict).
   The audit tools are checked against audit-pie.js / audit-source.js on the same inspection; the
   reference side of the audit is the diagnostics comparison in 1.

The page half (the live page's getPriorWeek, Compare rows and audit models against the edge runner) is
tests/test_connector_analyses_page.py, which needs a browser.

Discrimination: test_broken_variants_fail runs the same comparisons on deliberately broken inputs (the
prior week priced on Week N-2's inputs, the prior week equal to this week, a source dropped from the prior week,
the published charts read as Adjusted instead of Indexed, compare sides swapped); each must fail.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests.test_week_history import _fixture_today  # noqa: E402

RUNNER = ROOT / "tests" / "_edge_pipeline_runner.cjs"
DRIVER = ROOT / "tests" / "node" / "connector_analyses_driver.mjs"
NODE = ["node", "--experimental-strip-types", "--no-warnings"]
HISTORY = ROOT / "dist" / "assets" / "history"

SETTINGS = [("ppr", 12, 0), ("half_ppr", 10, 1), ("standard", 14, 0)]
SERIES = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "fantasycalc", "usatoday", "fantasypros", "cbs",
          "espn", "cbsros", "razzball"]
DDF = {"ddf_value": "blended", "ddf_value_charts": "charts", "ddf_value_projections": "projections"}
CHARTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
TOL = 1e-6


def run_edge(setting, mutate=None, drop_entry=None):
    """drop_entry: (week, source), that week's saved entry for that source left out of the history."""
    scoring, teams, sf = setting
    args = NODE + [str(RUNNER), "--scoring", scoring, "--teams", str(teams), "--superflex", str(sf),
                   "--dist", str(ROOT / "dist"), "--include", "series,prior,audit"]
    if mutate:
        args += ["--mutate", mutate]
    if drop_entry:
        args += ["--drop-entry", f"{drop_entry[0]}:{drop_entry[1]}"]
    env = {**os.environ, "TRADE_VALUE_TODAY": _fixture_today()}
    out = subprocess.run(args, capture_output=True, text=True, timeout=120, env=env)
    if out.returncode != 0:
        raise RuntimeError(f"edge runner failed: {out.stderr}")
    return json.loads(out.stdout)


def run_reference(setting, drop_entry=None):
    """The reference's page rows (Indexed tab), its prior week per series, and its diagnostics.
    drop_entry: as run_edge's."""
    import value_reference as ref
    today = date.fromisoformat(_fixture_today())
    inp = ref.Inputs.load(today=today)
    hist = ref.History(HISTORY)
    if drop_entry:
        week, key = drop_entry
        del hist.week_doc(week)["sources"][key]
    div = ref.load_divergence_exclusions(week=ref.freshness(inp)["current_week"])
    scoring, teams, sf = setting
    out = ref.compute(inp, {"scoring": scoring, "teams": teams, "superflex": sf}, views=("indexed",), hist=hist,
                      divergence_exclusions=div)
    s = ref.Setting(inp, scoring, teams, sf, hist=hist, divergence_exclusions=div)
    prior_rows = (s.prior_result() or {}).get("rows") or {}
    st = s.state()
    rows = {str(k): {key: v.get(key) for key in SERIES} for k, v in out["views"]["indexed"].items()}
    prior = {}
    for key in DDF:
        entry = out["prior"]["indexed"][key]
        prior[key] = ({"available": True, "values": {str(k): v for k, v in entry["values"].items()},
                       "currentValues": {str(k): v for k, v in entry["currentValues"].items()},
                       "currentWeek": entry["currentWeek"], "priorWeek": entry["priorWeek"]}
                      if entry["available"] else {"available": False, "reason": "no prior week"})
    week = st["current_week"]
    for key in SERIES:
        if key in DDF:
            continue
        field = "indexed" if key in CHARTS else "adjusted"
        values = {str(k): r[field].get(key) for k, r in prior_rows.items() if r[field].get(key) is not None}
        prior[key] = ({"available": True, "values": values, "currentWeek": week, "priorWeek": week - 1}
                      if values else {"available": False, "reason": f"not priced in Week {week - 1}"})
    return {"rows": rows, "prior": prior, "diagnostics": out["pipeline"], "week": week,
            "included": list(st["included"])}


def run_driver(edge, reference, setting, swap=False):
    with tempfile.TemporaryDirectory() as tmp:
        e, r = Path(tmp) / "edge.json", Path(tmp) / "ref.json"
        e.write_text(json.dumps(edge), encoding="utf-8")
        r.write_text(json.dumps({"rows": reference["rows"], "prior": reference["prior"]}), encoding="utf-8")
        scoring, teams, sf = setting
        args = NODE + [str(DRIVER), "--edge", str(e), "--reference", str(r), "--scoring", scoring,
                       "--teams", str(teams), "--superflex", str(sf)] + (["--swap", "1"] if swap else [])
        out = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if out.returncode != 0:
            raise RuntimeError(f"analyses driver failed: {out.stderr}")
        return json.loads(out.stdout)


def value_diffs(got: dict, want: dict, label: str) -> list[str]:
    """Players where two {player_key: value} maps disagree (a value on one side only counts)."""
    bad = []
    for k in sorted(set(got) | set(want)):
        a, b = got.get(k), want.get(k)
        if a is None and b is None:
            continue
        if a is None or b is None or abs(a - b) > TOL:
            bad.append(f"{label} {k}: edge {a}, reference {b}")
    return bad


def block_errors(edge: dict, reference: dict) -> list[str]:
    """Half 1: get-values' series, prior and audit blocks against the reference."""
    errors = []
    for key in SERIES:
        got = {k: v[key] for k, v in edge["series"].items() if key in v}
        want = {k: v[key] for k, v in reference["rows"].items() if v.get(key) is not None}
        errors += value_diffs(got, want, f"series {key}")
    prior = edge["prior"]
    if prior["current_week"] != reference["week"] or prior["prior_week"] != reference["week"] - 1:
        errors.append(f"prior pair {prior['prior_week']}->{prior['current_week']}, reference week {reference['week']}")
    for key in SERIES:
        got, want = prior["series"][key], reference["prior"][key]
        if got["available"] != want["available"]:
            errors.append(f"prior {key}: available {got['available']} vs {want['available']}")
            continue
        if got["available"]:
            errors += value_diffs(got["values"], want["values"], f"prior {key}")
    diag, want = edge["audit"]["valuePipeline"], reference["diagnostics"]
    if abs(diag["pie"] - want["pie"]) > TOL:
        errors.append(f"pie {diag['pie']} vs {want['pie']}")
    if sorted(diag["included"]) != sorted(want["included"]):
        errors.append(f"included {diag['included']} vs {want['included']}")
    for src, s in want["sources"].items():
        for pos, p in s["positions"].items():
            g = ((diag["sources"].get(src) or {}).get("positions") or {}).get(pos) or {}
            for f in ("listed", "starters", "rostered", "nEstimated"):
                if g.get(f) != p[f]:
                    errors.append(f"audit {src} {pos} {f}: edge {g.get(f)}, reference {p[f]}")
    return errors


def tool_errors(out: dict) -> list[str]:
    """Half 2: each tool's answer against the page module run on the reference (or the same inspection)."""
    errors = []
    for part in ("risers", "compare", "health", "source", "disagreements", "empty"):
        if out["tools"].get(part) != out["page"].get(part):
            if isinstance(out["tools"].get(part), dict):
                for k in sorted(set(out["tools"][part]) | set(out["page"][part])):
                    if out["tools"][part].get(k) != out["page"][part].get(k):
                        errors.append(f"{part} {k}: tool {json.dumps(out['tools'][part].get(k))[:300]} "
                                      f"page {json.dumps(out['page'][part].get(k))[:300]}")
            else:
                errors.append(f"{part}: tool {json.dumps(out['tools'][part])[:300]} page {json.dumps(out['page'][part])[:300]}")
    return errors


class ConnectorAnalysesParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # dist/ and its week history from the committed fixtures (make sync), as the parity tests build it.
        _render_env.ensure_built()
        if not HISTORY.joinpath("index.json").exists():
            raise AssertionError("make sync wrote no week history to dist/assets/history")
        cls.cases = {s: (run_edge(s), run_reference(s)) for s in SETTINGS}

    def test_blocks_match_reference(self):
        for setting, (edge, reference) in self.cases.items():
            with self.subTest(setting=setting):
                self.assertGreater(len(edge["series"]), 500)
                self.assertTrue(edge["prior"]["available"], edge["prior"]["reason"])
                self.assertGreater(len(edge["prior"]["series"]["ddf_value"]["values"]), 500)
                errors = block_errors(edge, reference)
                self.assertEqual(errors, [], f"{len(errors)} mismatches: {errors[:10]}")

    def test_tools_match_page_modules(self):
        for setting, (edge, reference) in self.cases.items():
            with self.subTest(setting=setting):
                out = run_driver(edge, reference, setting)
                ddf = out["tools"]["risers"]["ddf_value"]
                self.assertTrue(ddf["available"])
                self.assertGreater(ddf["counts"]["risers"] + ddf["counts"]["fallers"], 10)
                self.assertTrue(out["tools"]["disagreements"]["available"])
                self.assertGreaterEqual(len(out["tools"]["compare"]), 3)
                self.assertTrue(all(r["net"] is not None for r in out["tools"]["compare"][0]["rows"]))
                self.assertTrue(out["tools"]["health"])
                # JEG-1309: a source with no values has null totals and the page's line, never totals of 0.
                for src, e in out["tools"]["empty"].items():
                    self.assertEqual(e["totals"], {"published": None, "indexed": None, "adjusted": None}, src)
                    self.assertFalse(e["available"], src)
                errors = tool_errors(out)
                self.assertEqual(errors, [], f"{len(errors)} mismatches: {errors[:5]}")

    def test_unpaired_source_prior_pairs_on_included_set(self):
        # JEG-1029 review (P2): an included source with no Week N-1 snapshot. VP-1.2: I is the sources
        # with one, this week is run on I and the prior week on I, so the Δ is over one source set. The
        # current side must be the run on I, not get-values' full run (Codex: +5.9 for Josh Allen).
        setting = SETTINGS[0]
        week = self.cases[setting][1]["week"]
        drop = (week - 1, "fantasycalc")
        edge, reference = run_edge(setting, drop_entry=drop), run_reference(setting, drop_entry=drop)
        self.assertNotIn("fantasycalc", reference["included"])
        self.assertGreater(len(reference["included"]), 1)
        prior = edge["prior"]
        self.assertTrue(prior["available"], prior["reason"])
        self.assertEqual((prior["current_week"], prior["prior_week"]), (week, week - 1))
        self.assertFalse(prior["series"]["fantasycalc"]["available"])
        errors = []
        for key in SERIES:
            got, want = prior["series"][key], reference["prior"][key]
            if key == "fantasycalc":
                continue
            self.assertEqual(got["available"], want["available"], key)
            if not got["available"]:
                continue
            errors += value_diffs(got["values"], want["values"], f"prior {key}")
            # This week's side: the reference's rows, which are the run on I.
            now = {k: v[key] for k, v in reference["rows"].items() if v.get(key) is not None}
            if "current_values" not in got:
                errors.append(f"current {key}: no current_values")
                continue
            errors += value_diffs(got["current_values"], now, f"current {key}")
            if key in DDF:
                errors += value_diffs(got["current_values"], want["currentValues"], f"currentValues {key}")
        self.assertEqual(errors, [], f"{len(errors)} mismatches: {errors[:10]}")
        # risers_fallers on these blocks is the page's movers.js on the reference's pair.
        out = run_driver(edge, reference, setting)
        self.assertEqual(out["tools"]["risers"], out["page"]["risers"])

    def test_broken_variants_fail(self):
        setting = SETTINGS[0]
        edge, reference = self.cases[setting]

        def same_week(e):
            for key, entry in e["prior"]["series"].items():
                if entry["available"]:
                    entry["values"] = {k: v[key] for k, v in e["series"].items() if key in v}

        def drop_source(e):
            e["prior"]["series"]["fantasycalc"] = {"available": False, "reason": "dropped"}

        def adjusted_charts(e):
            for k, v in e["series"].items():
                for key in CHARTS:
                    if key in v and e["audit"]["rows"][k]["adjusted"].get(key) is not None:
                        v[key] = e["audit"]["rows"][k]["adjusted"][key]

        broken = {"prior week from Week N-2": run_edge(setting, mutate="two-weeks-back")}
        for name, fn in {"prior week equals this week": same_week, "a source dropped from the prior week": drop_source,
                         "charts read as Adjusted": adjusted_charts}.items():
            e = copy.deepcopy(edge)
            fn(e)
            broken[name] = e
        for name, e in broken.items():
            with self.subTest(variant=name):
                self.assertNotEqual(block_errors(e, reference), [], f"the block check did not catch: {name}")
        # The tool half on its own: a tool reading broken blocks no longer matches the page on the reference.
        for name in ("prior week equals this week", "charts read as Adjusted"):
            with self.subTest(variant=f"tool on {name}"):
                self.assertNotEqual(tool_errors(run_driver(broken[name], reference, setting)), [])
        with self.subTest(variant="compare sides swapped"):
            out = run_driver(edge, reference, setting, swap=True)
            self.assertNotEqual(out["tools"]["compare"], out["page"]["compare"])


if __name__ == "__main__":
    unittest.main()
