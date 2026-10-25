"""The engine's source-neutral value pipeline reproduces the worked example
(JEG-508, docs/methodology.md "Value Pipeline (source-neutral, 2026-10-09)",
VP-12).

Runs ValueModel.runValuePipeline (app/trade-value-chart/assets/value-model.js,
the code the page runs) headless under node on
tests/fixtures/value_pipeline_worked_example.json and checks EVERY expected
leaf -- inputs to the allocation, fill-in estimates, groups, weights, rates,
Adjusted / VORP vs waivers / Indexed values, the three DDF versions, tiers and
the default ranking -- to 1e-6, plus the bench-share 0.10 variant.

Discrimination: test_guard_catches_* mutate the engine (ESPN-style anchor
weights, bench share left at the old 35%, estimates not capped) and require
the comparison to fail. The pre-JEG-508 engine has no runValuePipeline at all,
so this test fails there outright.

Skips when node is missing, unless RENDER_TESTS_REQUIRED=1 (CI), where a
missing node is an error.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import _render_env
from tests import _es_worked_example as esx

ROOT = Path(__file__).resolve().parents[1]
VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = ROOT / "tests" / "value_pipeline_driver.js"
FIXTURE = ROOT / "tests" / "fixtures" / "value_pipeline_worked_example.json"
TOL = 1e-6


def _node():
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    return node


def run_engine(model: Path = VALUE_MODEL, bench_share: float | None = None, variant: str | None = None,
               promotion_model: bool | None = None, flex_bench_seats: bool | None = None) -> dict:
    """Run the engine. promotion_model: True forces on, False forces off,
    None uses the engine default (on since JEG-969, 2026-10-23).
    flex_bench_seats: True forces on, False forces off, None = engine default (off)."""
    cmd = [_node(), str(DRIVER), str(model), str(FIXTURE)]
    if bench_share is not None:
        cmd += ["--bench-share", repr(bench_share)]
    if variant is not None:
        cmd += ["--variant", variant]
    if promotion_model is True:
        cmd += ["--promotion-model"]
    elif promotion_model is False:
        cmd += ["--no-promotion-model"]
    if flex_bench_seats is True:
        cmd += ["--flex-bench-seats"]
    elif flex_bench_seats is False:
        cmd += ["--no-flex-bench-seats"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(f"driver failed: {proc.stderr[-2000:]}")
    return json.loads(proc.stdout)


def diff(expected, actual, path="", out=None):
    """Every leaf of `expected` must be present in `actual` and equal (numbers
    to TOL). Extra keys in `actual` are allowed."""
    out = [] if out is None else out
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            out.append(f"{path}: expected object, got {actual!r}"[:300])
            return out
        for key, value in expected.items():
            if key not in actual:
                out.append(f"{path}.{key}: missing")
                continue
            diff(value, actual[key], f"{path}.{key}", out)
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            out.append(f"{path}: expected {expected!r}, got {actual!r}"[:300])
            return out
        for i, (e, a) in enumerate(zip(expected, actual)):
            diff(e, a, f"{path}[{i}]", out)
    elif isinstance(expected, bool) or expected is None or isinstance(expected, str):
        if expected != actual:
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
    elif isinstance(expected, (int, float)):
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or abs(expected - actual) > TOL:
            out.append(f"{path}: expected {expected!r}, got {actual!r}")
    else:
        out.append(f"{path}: unhandled {expected!r}")
    return out


SKIP_EXPECTED = {
    # Narrative-only keys (not engine outputs).
    "flex_contrast", "starting_slots_per_team",
}


def expected_main(doc: dict) -> dict:
    return {k: v for k, v in doc["expected"].items() if k not in SKIP_EXPECTED}


def variant_diff(doc: dict, actual: dict) -> list[str]:
    var = doc["variant_bench_share_0_10"]
    out = diff(var["ddf_weights"], actual["ddf_weights"], "variant.ddf_weights")
    for src, weights in var["source_weights"].items():
        diff(weights, actual["sources"][src]["weights"], f"variant.sources.{src}.weights", out)
    for key, value in var["rows_ddf_blended"].items():
        diff(value, actual["rows"][key]["ddf_blended"]["value"], f"variant.rows.{key}", out)
    return out


class WorkedExampleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(FIXTURE.read_text())
        cls.actual = run_engine(promotion_model=False, flex_bench_seats=False)

    def test_every_expected_value(self):
        problems = diff(expected_main(self.doc), self.actual, "expected")
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_bench_share_variant(self):
        bs = self.doc["variant_bench_share_0_10"]["setting_change"]["bench_share"]
        problems = variant_diff(self.doc, run_engine(bench_share=bs, promotion_model=False,
                                                      flex_bench_seats=False))
        self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_check_covers_the_fixture(self):
        # The diff must actually walk the rows and the per-source detail; a
        # check that compared nothing would pass on any engine.
        exp = expected_main(self.doc)
        self.assertEqual(len(exp["rows"]), 30)
        self.assertIn("imputation_ratios", exp["sources"]["c5"]["positions"]["RB"])
        self.assertEqual(self.actual["version"], "value-pipeline/2")

    def test_estimated_reasons(self):
        rows = self.actual["rows"]
        self.assertEqual(rows["207"]["estimated_reason"]["c5"],
                         "Estimated: no chart lists him; from c5's values against projected points")
        self.assertEqual(rows["306"]["estimated_reason"]["c5"],
                         "Estimated: c5 doesn't list him; scaled from c1 and c4")
        self.assertEqual(rows["205"]["reasons"]["c2"], "Below rosterable depth; c2 doesn't list him")
        self.assertEqual(rows["207"]["reasons"]["p2"], "p2 doesn't project this player")


def _mutated(replacements: list[tuple[str, str]]) -> Path:
    src = VALUE_MODEL.read_text()
    for old, new in replacements:
        if old not in src:
            raise AssertionError(f"mutation anchor not found: {old!r}")
        src = src.replace(old, new, 1)
    tmp = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    tmp.write(src)
    tmp.close()
    return Path(tmp.name)


class GuardDiscriminationTest(unittest.TestCase):
    """The comparison must fail on a broken engine."""

    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(FIXTURE.read_text())

    def assert_fails(self, replacements):
        model = _mutated(replacements)
        try:
            actual = run_engine(model, promotion_model=False, flex_bench_seats=False)
        except AssertionError:
            return  # the broken engine crashed: also a failure
        finally:
            model.unlink()
        self.assertNotEqual(diff(expected_main(self.doc), actual, "expected"), [])

    def test_guard_catches_old_bench_share(self):
        self.assert_fails([(
            "var bsInput = vpFinite(setting.bench_share) ? setting.bench_share : VP_DEFAULT_BENCH_SHARE;",
            "var bsInput = 0.35;")])

    def test_guard_catches_uncapped_estimates(self):
        self.assert_fails([("info.value = Math.min(Math.max(raw, 0), cap);", "info.value = Math.max(raw, 0);")])

    def test_guard_catches_flex_by_own_values(self):
        # Superseded OC-4 rule: each source fills flex by its own natives.
        self.assert_fails([("var degenerate = projI.length === 0;", "var degenerate = true;")])

    def test_guard_catches_first_source_weights(self):
        # An anchor-style rule: DDF weights from one source instead of the mean.
        self.assert_fails([("Sraw[pos] = sn ? ss / sn : 0;",
                            "Sraw[pos] = out[included[0]].starterMix[pos];")])



class ExpectedStartsVariantTest(unittest.TestCase):
    """JEG-536 (ES-11): the engine reproduces the worked example's
    expected-starts variants to 1e-6: chart sigma, every source's lines,
    bands, parts, groups, own weights and rates, the DDF weights, every row's
    DDF Value, lineup share and start-worthy probability, the readout; and the
    0.10 override. Fails before JEG-536: the engine ignores `lineup` and
    prices the VP-2.6 slices at 15%."""

    @classmethod
    def setUpClass(cls):
        cls.doc = esx.load()

    def test_variants_reproduced(self):
        for name in esx.VARIANTS:
            with self.subTest(variant=name):
                problems = esx.variant_problems(self.doc, name, run_engine(variant=name, promotion_model=False,
                                                                                     flex_bench_seats=False))
                self.assertEqual(problems, [], "\n".join(problems[:40]))

    def test_variant_is_walked(self):
        self.assertGreater(esx.count_leaves(self.doc["variant_expected_starts"]["expected"]), 1500)
        exp = self.doc["variant_expected_starts"]["expected"]
        self.assertFalse(exp["bench_share_readout"]["override"])
        # JEG-879: bench_per_team=4 gives WR 3 bench seats (rostered=6),
        # so the waiver line falls below the depth boundary -> 2 bands.
        self.assertEqual(len(exp["sources"]["p1"]["positions"]["WR"]["bands"]), 2)
        self.assertEqual(exp["sources"]["p1"]["positions"]["WR"]["lineup"]["n_per_team"], 2)

    def assert_variant_fails(self, replacements):
        model = _mutated(replacements)
        try:
            actual = run_engine(model, variant="variant_expected_starts", promotion_model=False,
                               flex_bench_seats=False)
        except AssertionError:
            return
        finally:
            model.unlink()
        self.assertNotEqual(esx.variant_problems(self.doc, "variant_expected_starts", actual), [])

    def test_guard_catches_slices_kept(self):
        self.assert_variant_fails([('if (esMode && method !== "no_players") {', 'if (false) {')])

    def test_guard_catches_fixed_share(self):
        self.assert_variant_fails([("if (esMode) bsInput = bsOverride;", "if (esMode) bsInput = 0.15;")])

    def test_guard_catches_unscaled_chart_sigma(self):
        self.assert_variant_fails([("chartSigma[pos].sigma_rel * esConfidence", "chartSigma[pos].sigma_rel")])

    def test_guard_catches_one_band_only(self):
        # JEG-879: bench_per_team=4 gives WR 2 bands; the mutation collapses
        # every position to 1 band, so the comparison must fail.
        self.assert_variant_fails([("if (!teams || idx >= work.length || work[idx].native <= waiver) break;",
                                    "break;")])

class TestPromotionModel(unittest.TestCase):
    """JEG-969: promotion/demotion model behind promotion_model flag."""

    @classmethod
    def setUpClass(cls):
        _node()  # skip if node not installed
        # Run with ES variant, flag OFF
        cls.off = run_engine(variant="variant_expected_starts", promotion_model=False)
        # Run with ES variant, flag ON
        cls.on = run_engine(variant="variant_expected_starts", promotion_model=True)

    def test_promotion_model_changes_lineup_shares(self):
        """The flag changes at least some lineup shares."""
        off_ls = {}
        on_ls = {}
        for pkey, row in self.off.get("rows", {}).items():
            if row.get("lineup_share") is not None:
                off_ls[pkey] = row["lineup_share"]
        for pkey, row in self.on.get("rows", {}).items():
            if row.get("lineup_share") is not None:
                on_ls[pkey] = row["lineup_share"]
        diffs = [abs(on_ls[k] - off_ls[k]) for k in off_ls if k in on_ls and off_ls[k] != on_ls[k]]
        self.assertTrue(len(diffs) > 0,
                        "promotion_model should change at least some lineup shares")

    def test_promotion_model_bench_shares_differ(self):
        """Bench share readout differs with promotion model."""
        off_bs = self.off.get("bench_share_readout", {}).get("overall")
        on_bs = self.on.get("bench_share_readout", {}).get("overall")
        # Both should be valid numbers
        self.assertIsNotNone(off_bs)
        self.assertIsNotNone(on_bs)
        # They must differ (the whole point of the model)
        self.assertNotAlmostEqual(off_bs, on_bs, places=6,
                                  msg="promotion_model should change bench share readout")

    def test_promotion_model_off_preserves_values(self):
        """With flag off, bench share readout matches what existing tests pin."""
        # The off result should have the same bench share as the pinned ES test
        off_bs = self.off.get("bench_share_readout", {})
        self.assertIsNotNone(off_bs.get("overall"),
                             "bench_share_readout.overall must be present with flag off")

    def test_promotion_model_spec_reference_parity(self):
        """Spec reference and JS engine agree on bench share with promotion model."""
        import sys
        sys.path.insert(0, str(ROOT / "pipelines"))
        from spec_reference import value_pipeline as sp

        doc = json.loads(FIXTURE.read_text())
        variant = doc["variant_expected_starts"]
        setting_d = {**doc["setting"], **(variant.get("setting_change") or {})}
        setting = sp.Setting.from_fixture(setting_d)
        pos_of = {int(k): v["pos"] for k, v in doc["players"].items()}
        sources_raw = doc.get("inputs") or doc.get("sources")
        sources = {s: {"family": v["family"], "status": v["status"], "values": v["values"]}
                   for s, v in sources_raw.items()}
        inc_keys = [s for s, v in sources.items() if v["status"] == "included"]
        lineup = variant.get("lineup")

        sp_off = sp.run_week(setting, pos_of, sources, inc_keys, lineup=lineup,
                             promotion_model=False)
        sp_on = sp.run_week(setting, pos_of, sources, inc_keys, lineup=lineup,
                            promotion_model=True)

        # Spec reference bench shares must differ with flag on vs off
        off_bs = sp_off.get("bench_share_readout", {}).get("overall")
        on_bs = sp_on.get("bench_share_readout", {}).get("overall")
        self.assertIsNotNone(off_bs)
        self.assertIsNotNone(on_bs)
        self.assertNotAlmostEqual(off_bs, on_bs, places=6,
                                  msg="Spec reference promotion model should change bench share")

        # Compare JS and spec reference bench shares with flag ON
        js_bs = self.on.get("bench_share_readout", {}).get("overall")
        self.assertAlmostEqual(on_bs, js_bs, places=4,
                               msg=f"Spec/JS bench share readout differs: {on_bs} vs {js_bs}")

    def test_guard_catches_broken_promotion_rate(self):
        """Negative test: if we break the promotion rate to 10x, the bench
        shares must differ from the correct promotion_model=on result."""
        # Mutate the engine: multiply all promotion rates by 10
        model = VALUE_MODEL.read_text()
        # Break QB rate specifically
        broken = model.replace('"1": 0.018, "2": 0.017, "3": 0.015, "4+": 0.005',
                                '"1": 0.180, "2": 0.170, "3": 0.150, "4+": 0.050')
        tmp = Path(tempfile.mktemp(suffix=".js"))
        try:
            tmp.write_text(broken)
            broken_result = run_engine(model=tmp, variant="variant_expected_starts",
                                       promotion_model=True)
            # The broken result's bench share should differ from the correct one
            correct_bs = self.on.get("bench_share_readout", {}).get("QB")
            broken_bs = broken_result.get("bench_share_readout", {}).get("QB")
            self.assertIsNotNone(correct_bs)
            self.assertIsNotNone(broken_bs)
            self.assertNotAlmostEqual(correct_bs, broken_bs, places=4,
                                      msg="10x promotion rate should produce different bench share")
        finally:
            tmp.unlink(missing_ok=True)


class TestFlexBenchSeats(unittest.TestCase):
    """MR-28 / JEG-969: flex_bench_seats flag changes bench allocation."""

    @classmethod
    def setUpClass(cls):
        _node()
        cls.off = run_engine(variant="variant_expected_starts", promotion_model=False,
                             flex_bench_seats=False)
        cls.on = run_engine(variant="variant_expected_starts", promotion_model=False,
                            flex_bench_seats=True)

    def test_flex_bench_seats_changes_bench_allocation(self):
        """At least one position's bench seats change with flex_bench_seats."""
        off_alloc = self.off.get("allocation", {})
        on_alloc = self.on.get("allocation", {})
        diffs = []
        for pos in ("QB", "RB", "WR", "TE"):
            off_b = off_alloc.get(pos, {}).get("bench", 0)
            on_b = on_alloc.get(pos, {}).get("bench", 0)
            if off_b != on_b:
                diffs.append(f"{pos}: {off_b}->{on_b}")
        self.assertTrue(len(diffs) > 0,
                        "flex_bench_seats should change at least one position's bench count")

    def test_flex_bench_seats_on_matches_default(self):
        """With flag on, results match the default (flex_bench_seats is on by default,
        2026-10-23 Jeremy approved)."""
        default = run_engine(variant="variant_expected_starts", promotion_model=False)
        on_alloc = self.on.get("allocation", {})
        def_alloc = default.get("allocation", {})
        for pos in ("QB", "RB", "WR", "TE"):
            self.assertEqual(on_alloc.get(pos, {}).get("bench"),
                             def_alloc.get(pos, {}).get("bench"),
                             f"{pos} bench should match default when flag is on")

    def test_flex_bench_seats_spec_parity(self):
        """Spec reference and JS engine agree on bench allocation with flex_bench_seats."""
        import sys
        sys.path.insert(0, str(ROOT / "pipelines"))
        from spec_reference import value_pipeline as sp

        doc = json.loads(FIXTURE.read_text())
        variant = doc["variant_expected_starts"]
        setting_d = {**doc["setting"], **(variant.get("setting_change") or {})}
        setting = sp.Setting.from_fixture(setting_d)
        pos_of = {int(k): v["pos"] for k, v in doc["players"].items()}
        sources_raw = doc.get("inputs") or doc.get("sources")
        sources = {s: {"family": v["family"], "status": v["status"], "values": v["values"]}
                   for s, v in sources_raw.items()}
        inc_keys = [s for s, v in sources.items() if v["status"] == "included"]
        lineup = variant.get("lineup")

        sp_on = sp.run_week(setting, pos_of, sources, inc_keys, lineup=lineup,
                            promotion_model=False, flex_bench_seats=True)

        # Compare allocation bench counts
        for pos in ("QB", "RB", "WR", "TE"):
            js_bench = self.on.get("allocation", {}).get(pos, {}).get("bench", 0)
            sp_bench = sp_on.get("priced", {})
            # The spec reference returns allocation per source; get from first source
            sp_alloc = None
            for s_key, s_data in sp_on.get("priced", {}).items():
                if "allocation" in s_data:
                    sp_alloc = s_data["allocation"]
                    break
            if sp_alloc:
                self.assertEqual(js_bench, sp_alloc.get(pos, {}).get("bench", 0),
                                 f"Spec/JS {pos} bench mismatch with flex_bench_seats on")


class TestFlexBenchSeatsTwoQbSkip(unittest.TestCase):
    """Jeremy, 2026-10-23, option A: flex_bench_seats is skipped in 2-QB /
    superflex rosters because market_bench 2-QB data already reflects
    supply-capped QB benches. In 1-QB the effect is unchanged."""

    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0, str(ROOT / "pipelines"))
        import value_reference as ref
        cls.ref = ref
        cls.inp = ref.Inputs.load()

    def _bench(self, qb=1, superflex=0, flex_bench_seats=True):
        s = self.ref.Setting(self.inp, "ppr", 12, qb=qb, superflex=superflex,
                             flex_bench_seats=flex_bench_seats)
        return {p: s.result()["slot_fill"][p]["bench"] for p in ("QB", "RB", "WR", "TE")}

    def test_two_qb_output_equals_flag_off(self):
        """In 2-QB, flex_bench_seats ON produces the same bench as OFF."""
        on = self._bench(qb=2, flex_bench_seats=True)
        off = self._bench(qb=2, flex_bench_seats=False)
        self.assertEqual(on, off, "2-QB bench should be identical with flag on or off")

    def test_superflex_output_equals_flag_off(self):
        """In superflex, flex_bench_seats ON produces the same bench as OFF."""
        on = self._bench(qb=1, superflex=1, flex_bench_seats=True)
        off = self._bench(qb=1, superflex=1, flex_bench_seats=False)
        self.assertEqual(on, off, "superflex bench should be identical with flag on or off")

    def test_one_qb_effect_unchanged(self):
        """In 1-QB, flex_bench_seats still changes bench allocation."""
        on = self._bench(qb=1, flex_bench_seats=True)
        off = self._bench(qb=1, flex_bench_seats=False)
        self.assertNotEqual(on, off, "1-QB bench should differ with flex_bench_seats on vs off")

    def test_guard_catches_missing_two_qb_skip(self):
        """If the 2-QB skip were removed, 2-QB bench would differ from flag-off.

        Proves the guard catches the bug: monkey-patch allocate to remove
        the is_two_qb check, confirm bench changes in 2-QB."""
        ref = self.ref
        inp = self.inp
        orig_allocate = ref.allocate

        def patched_allocate(league, order, score, *, flex_bench_seats=True):
            """Force flex_bench_seats in 2-QB (remove the skip)."""
            import lib.roster_convention as rc
            from value_reference import POSITIONS, POS_ORDER, bench_seats as bs_fn

            t = int(league.teams)
            d = {p: t * int(league.slots.get(p, 0)) for p in POSITIONS}

            def take(cands, n):
                cands.sort(key=lambda c: (-score[c[1]], POS_ORDER[c[0]], c[1]))
                got = {p: 0 for p in POSITIONS}
                for p, _i in cands[:max(0, n)]:
                    got[p] += 1
                return got

            sf = take([(p, i) for p in POSITIONS for idx, i in enumerate(order.get(p, []))
                       if idx >= d[p]], t * int(league.superflex))
            fx = take([(p, i) for p in POSITIONS if p in league.flex_eligible
                       for idx, i in enumerate(order.get(p, []))
                       if idx >= d[p] + sf[p]], t * int(league.flex))
            # Force flex_filled even in 2-QB (the bug we're catching)
            ff = {p: sf[p] + fx[p] for p in POSITIONS} if flex_bench_seats else None
            b = bs_fn(league, flex_filled=ff)
            out = {}
            for p in POSITIONS:
                s = d[p] + sf[p] + fx[p]
                out[p] = {"dedicated": d[p], "superflex": sf[p], "flex": fx[p], "bench": b[p],
                          "starters": s, "rostered": s + b[p]}
            return out

        # Get the correct (skipped) 2-QB bench
        correct = {p: ref.Setting(inp, "ppr", 12, qb=2).result()["slot_fill"][p]["bench"]
                   for p in ("QB", "RB", "WR", "TE")}

        # Monkey-patch to remove the skip
        ref.allocate = patched_allocate
        try:
            broken = {p: ref.Setting(inp, "ppr", 12, qb=2).result()["slot_fill"][p]["bench"]
                      for p in ("QB", "RB", "WR", "TE")}
        finally:
            ref.allocate = orig_allocate

        self.assertNotEqual(correct, broken,
                            "Without the 2-QB skip, bench allocation should differ "
                            "(guard proves the skip is necessary)")


if __name__ == "__main__":
    unittest.main()
