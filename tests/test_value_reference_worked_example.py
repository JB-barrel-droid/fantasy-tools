"""JEG-508: the Python reference reproduces the value pipeline's worked example.

docs/methodology.md "Value Pipeline (source-neutral, 2026-10-09)", VP-12:
each implementation must reproduce tests/fixtures/value_pipeline_worked_example.json
(schema /2) to 1e-6 before it runs on live data. This test runs
pipelines/value_reference.run_pipeline on the fixture's inputs and checks
every intermediate and expected value it holds: mean points per game, the
league allocation (and the flex contrast with c1's own values), fill sets,
every estimate (ratio and curve paths, peers, fit players, caps), each
source's lines, slices, groups, mixes, weights, rates and per-player values,
the DDF weights and budgets, the Indexed factors and values, slot fill, tiers,
the default ranking, every row (three DDF versions, estimated flags), and the
bench-share-0.10 variant.

Discrimination: the mutation tests below re-run the pipeline with one rule
broken at a time (the superseded flex-by-own-values rule, no fill-in, a mean
instead of the median over peers, the old 16-per-rostered-slot pie, a 35%
bench share) and require the checker to report mismatches for each. The
pre-JEG-508 reference (git 15292b6a) has no pipeline at all: it cannot run on
the fixture (no run_pipeline; its values are ESPN-anchored).
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import value_reference as ref  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "value_pipeline_worked_example.json"
TOL = 1e-6


def load():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def league_of(fx: dict, bench_share: float | None = None) -> ref.League:
    s = fx["setting"]
    return ref.League(teams=s["teams"], slots=dict(s["slots"]), flex=s["flex"], superflex=s["superflex"],
                      bench=s["bench_per_team"],
                      bench_share=s["bench_share"] if bench_share is None else bench_share,
                      flex_eligible=tuple(s["flex_eligible"]))


def sources_of(fx: dict) -> dict:
    return {k: ref.SourceInput(k, v["family"], {int(i): float(x) for i, x in v["values"].items()})
            for k, v in fx["inputs"].items()}


def run(fx: dict, bench_share: float | None = None) -> dict:
    pos_of = {int(i): p["pos"] for i, p in fx["players"].items()}
    included = [k for k, v in fx["inputs"].items() if v["status"] == "included"]
    return ref.run_pipeline(league_of(fx, bench_share), sources_of(fx), pos_of, included)


def norm(obj):
    """Result -> fixture shape: dict keys as strings, tuples as lists."""
    if isinstance(obj, dict):
        return {str(k): norm(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [norm(v) for v in obj]
    return obj


# Objects whose key set must match exactly (an extra estimate, peer, row or
# listed player is as wrong as a missing one).
STRICT_KEYS = {"estimated", "imputation_ratios", "peers", "players", "rows", "values", "adjusted",
               "vorp_vs_waivers", "indexed", "mean_ppg", "fill_sets", "rows_ddf_blended"}


def diff(expected, actual, path="", out=None):
    """Every expected value must be present in actual and equal (numbers to
    TOL). Returns a list of mismatch strings."""
    out = [] if out is None else out
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            out.append(f"{path}: expected object, got {actual!r}"[:300])
            return out
        name = path.rsplit("/", 1)[-1]
        if name in STRICT_KEYS and set(expected) != set(actual):
            out.append(f"{path}: keys {sorted(set(actual) ^ set(expected))} differ")
        for k, v in expected.items():
            if k not in actual:
                out.append(f"{path}/{k}: missing")
                continue
            diff(v, actual[k], f"{path}/{k}", out)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            out.append(f"{path}: expected {expected!r} got {actual!r}"[:300])
            return out
        for n, (e, a) in enumerate(zip(expected, actual)):
            diff(e, a, f"{path}[{n}]", out)
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if expected != actual:
            out.append(f"{path}: expected {expected!r} got {actual!r}")
    elif isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual) \
                or abs(expected - actual) > TOL:
            out.append(f"{path}: expected {expected!r} got {actual!r}")
    return out


SOURCE_FIELDS = ("family", "positions", "groups", "total_vorp", "players", "weights", "starter_mix",
                 "bench_mix", "rates", "unfunded_moved", "vorp_display_factor")


def actual_rows(fx: dict, res: dict) -> dict:
    out = {}
    for i, r in res["rows"].items():
        out[str(i)] = {
            "name": fx["players"][str(i)]["name"], "pos": r["pos"],
            "adjusted": r["adjusted"], "vorp_vs_waivers": r["vorp_vs_waivers"], "estimated": r["estimated"],
            **{f"ddf_{v}": {k: r["ddf"][v][k] for k in ("value", "count", "low_confidence", "sources")}
               for v in ("blended", "charts", "projections")},
            "indexed": r["indexed"], "ddf_tier": r["ddf_tier"], "mean_ppg": r["mean_ppg"],
        }
    return norm(out)


def check(fx: dict, res: dict, variant: dict | None = None) -> list[str]:
    """Mismatches of a pipeline result against the fixture's expected block
    (and, when given, the bench-share-0.10 variant run)."""
    e = fx["expected"]
    a = norm(res)
    bad = []
    for key in ("included", "pie", "starting_slots_per_team", "bench_share_applied", "mean_ppg", "allocation",
                "fill_sets", "starter_mix_mean", "bench_mix_mean", "ddf_weights", "group_budgets", "indexed",
                "default_ranking"):
        diff(e[key], a.get(key), key, bad)
    diff(e["slot_fill_mean_ppg"], a.get("slot_fill"), "slot_fill_mean_ppg", bad)
    for src, exp in e["sources"].items():
        got = a["sources"].get(src) or {}
        diff({k: exp[k] for k in SOURCE_FIELDS}, got, f"sources/{src}", bad)
        if (exp["status"] == "included") != (got.get("status") == "included"):
            bad.append(f"sources/{src}/status: expected {exp['status']} got {got.get('status')}")
    diff(e["rows"], actual_rows(fx, res), "rows", bad)
    # The flex contrast: by projected points (the rule) and by c1's own values
    # (the superseded rule), both from the same allocation function.
    diff(e["flex_contrast"]["by_mean_projected_points"],
         {p: v["flex"] for p, v in a["allocation"].items()}, "flex_contrast/by_mean", bad)
    c1 = sources_of(fx)["c1"].values
    pos_of = {int(i): p["pos"] for i, p in fx["players"].items()}
    own = {p: sorted((i for i in c1 if pos_of[i] == p), key=lambda i: (-c1[i], i)) for p in ref.POSITIONS}
    c1_alloc = ref.allocate(league_of(fx), own, c1)
    diff(e["flex_contrast"]["c1_by_own_values_superseded"], {p: v["flex"] for p, v in c1_alloc.items()},
         "flex_contrast/c1_own", bad)
    if variant is not None:
        v = fx["variant_bench_share_0_10"]
        av = norm(variant)
        diff(v["source_weights"], {k: av["sources"][k]["weights"] for k in v["source_weights"]},
             "variant/source_weights", bad)
        diff(v["ddf_weights"], av["ddf_weights"], "variant/ddf_weights", bad)
        diff(v["rows_ddf_blended"], {i: r["ddf"]["blended"]["value"] for i, r in av["rows"].items()},
             "variant/rows_ddf_blended", bad)
    return bad


def count_expected_numbers(obj) -> int:
    if isinstance(obj, dict):
        return sum(count_expected_numbers(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(count_expected_numbers(v) for v in obj)
    return 1 if isinstance(obj, (int, float)) and not isinstance(obj, bool) else 0


class WorkedExample(unittest.TestCase):
    def test_schema(self):
        fx = load()
        self.assertEqual(fx["schema"], "value-pipeline-worked-example/2")

    def test_reproduces_every_expected_value(self):
        fx = load()
        bench = fx["variant_bench_share_0_10"]["setting_change"]["bench_share"]
        bad = check(fx, run(fx), run(fx, bench))
        n = count_expected_numbers(fx["expected"]) + count_expected_numbers(fx["variant_bench_share_0_10"])
        print(f"\n[JEG-508 worked example] {n} expected numbers, {len(bad)} mismatches at {TOL}")
        self.assertEqual(bad, [], "\n".join(bad[:40]))

    def test_hand_check_values(self):
        """The spec's own hand-check: p1 RB Delta Adjusted 47.910397 and RB
        Delta's three DDF versions."""
        res = run(load())
        self.assertAlmostEqual(res["sources"]["p1"]["players"][201]["adjusted"], 47.910397, places=6)
        ddf = res["rows"][201]["ddf"]
        self.assertAlmostEqual(ddf["blended"]["value"], 48.511113, places=6)
        self.assertAlmostEqual(ddf["charts"]["value"], 50.223260, places=6)
        self.assertAlmostEqual(ddf["projections"]["value"], 45.086821, places=6)
        bench = sum(v for g, v in res["ddf_weights"].items() if g.endswith("|bench"))
        self.assertAlmostEqual(bench, 0.15, places=12)

    def test_every_source_total_equals_the_pie(self):
        """VP-5.5/5.6 by construction: Adjusted and VORP vs waivers totals
        over each source's work list equal the pie."""
        res = run(load())
        for key, d in res["sources"].items():
            adj = sum(p["adjusted"] for p in d["players"].values())
            vorp = sum(p["vorp_display"] for p in d["players"].values())
            self.assertAlmostEqual(adj, res["pie"], places=6, msg=key)
            self.assertAlmostEqual(vorp, res["pie"], places=6, msg=key)


class IndexedNullRule(unittest.TestCase):
    """VP-6.4 as ruled in spec PR #484: the Indexed factor is null when the
    shared native sum <= 0, the shared DDF Value sum <= 0, or nothing is
    shared, and then the chart's whole Indexed column is null, players below
    rosterable depth included."""

    def _run(self, chart_values):
        pos_of = {1: "RB", 2: "RB", 3: "RB", 4: "RB", 5: "RB"}
        league = ref.League(teams=1, slots={"QB": 0, "RB": 1, "WR": 0, "TE": 0}, flex=0, bench=1)
        # Equal projections: every player sits on the waiver line, so every
        # Adjusted value and every DDF Value is 0.
        sources = {"p": ref.SourceInput("p", "projection", {i: 5.0 for i in pos_of}),
                   "c": ref.SourceInput("c", "chart", dict(chart_values))}
        return ref.run_pipeline(league, sources, pos_of, ["p", "c"])

    def test_ddf_sum_zero_gives_null_for_the_whole_chart(self):
        res = self._run({1: 10.0, 2: 10.0, 3: 10.0})
        self.assertEqual(res["indexed"]["c"]["ddf_total"], 0.0)
        self.assertGreater(res["indexed"]["c"]["native_total"], 0.0)
        self.assertIsNone(res["indexed"]["c"]["factor"])
        # Listed, estimated and below-depth players alike.
        self.assertEqual({i: r["indexed"]["c"] for i, r in res["rows"].items()}, {i: None for i in res["rows"]})

    def test_native_sum_zero_gives_null(self):
        res = self._run({1: 0.0, 2: 0.0, 3: 0.0})
        self.assertIsNone(res["indexed"]["c"]["factor"])
        self.assertTrue(all(r["indexed"]["c"] is None for r in res["rows"].values()))


class CheckerCatchesBrokenRules(unittest.TestCase):
    """Each broken rule must make the worked-example check fail."""

    def _bad(self, **patches):
        fx = load()
        with mock.patch.multiple(ref, **patches):
            return check(fx, run(fx))

    def test_flex_by_own_values(self):
        real = ref.allocate

        def own_values_allocate(league, order, score):
            # The superseded rule: no shared league allocation; signal by
            # pushing every flex slot to RB.
            out = real(league, order, score)
            for p in ("WR", "TE"):
                out["RB"]["flex"] += out[p]["flex"]
                out["RB"]["starters"] += out[p]["flex"]
                out["RB"]["rostered"] += out[p]["flex"]
                out[p]["starters"] -= out[p]["flex"]
                out[p]["rostered"] -= out[p]["flex"]
                out[p]["flex"] = 0
            return out
        self.assertTrue(self._bad(allocate=own_values_allocate))

    def test_no_fill_in(self):
        self.assertTrue(self._bad(_estimate=lambda *a, **k: {"path": "none", "peers": {}, "cap": 0, "raw": 0,
                                                             "value": -1e9, "capped": False}))

    def test_mean_instead_of_median(self):
        self.assertTrue(self._bad(median=lambda v: sum(v) / len(v)))

    def test_fit_window(self):
        self.assertTrue(self._bad(ESTIMATE_FIT_N=5))

    def test_pie_per_rostered_slot(self):
        self.assertTrue(self._bad(PIE_PER_STARTING_SLOT=16.0))

    def test_bench_share_35(self):
        fx = load()
        self.assertTrue(check(fx, run(fx, 0.35)))


if __name__ == "__main__":
    unittest.main()
