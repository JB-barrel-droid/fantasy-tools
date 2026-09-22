"""Tests for the reference-compute stage: isotonic reindex + fixed-pie indexing.

Every audit is negative-tested against its named defect. Hermetic: synthetic
fixtures only, except the final smoke test which runs the real fixture pair
(usatoday candidate -> ESPN-leg anchor) and asserts internal consistency.
"""
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))
from isotonic import isotonic_fit, isotonic_predict  # noqa: E402
import reindex_comparison_section as rcs  # noqa: E402

POS = ("QB", "RB", "WR", "TE")


def make_players(tmp, per_pos=12):
    players = {"meta": {}, "players": []}
    for i, pos in enumerate(POS):
        for j in range(per_pos):
            players["players"].append(
                {"name": f"Player {pos}{j}", "pos": pos,
                 "player_key": 1000 + i * 100 + j})
    p = tmp / "players.json"
    p.write_text(json.dumps(players))
    return p, players


def make_fixture(tmp, players, anchor_fn):
    """Anchor leg shaped like the fixture's ESPN section."""
    combos = {"full_12": {"values": {}, "native": {}, "n": {}, "index_total": {}}}
    for pl in players["players"]:
        slug = pl["name"].lower()
        combos["full_12"]["values"][slug] = anchor_fn(pl)
        combos["full_12"]["native"][slug] = anchor_fn(pl)
    fx = {"sources": {"espn": {"combos": combos}}}
    p = tmp / "fixture.json"
    p.write_text(json.dumps(fx))
    return p


def make_candidate(tmp, source, players, native_fn, combos=("full_12",)):
    cand = {"schema": "trade-value-source-reference-v1", "source_key": source,
            "asof": "2026-09-21", "combos": {}}
    for combo in combos:
        native, keys = {}, {}
        for pl in players["players"]:
            slug = pl["name"].lower()
            v = native_fn(pl)
            if v is not None:
                native[slug] = v
                keys[slug] = pl["player_key"]
        cand["combos"][combo] = {"native": native, "player_keys": keys}
    p = tmp / f"{source}-candidate.json"
    p.write_text(json.dumps(cand))
    return p


def run_stage(candidate, fixture, players):
    return rcs.reindex_section(str(candidate), str(fixture), str(players))


class TestIsotonicMath(unittest.TestCase):
    def test_fit_is_non_decreasing(self):
        xs = [5, 1, 4, 2, 3, 0]
        ys = [9, 1, 2, 8, 3, 0]
        fx, fy = isotonic_fit(xs, ys)
        self.assertTrue(all(b >= a for a, b in zip(fy, fy[1:])),
                        "fitted values must be non-decreasing")

    def test_predict_monotone_and_clamped(self):
        fx, fy = isotonic_fit([1, 2, 3], [10, 5, 7])
        lo = isotonic_predict(fx, fy, -100)
        hi = isotonic_predict(fx, fy, 100)
        mid = [isotonic_predict(fx, fy, x) for x in (1, 1.5, 2, 2.5, 3)]
        self.assertTrue(all(b >= a for a, b in zip(mid, mid[1:])))
        self.assertEqual(lo, fy[0])
        self.assertEqual(hi, fy[-1])

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            isotonic_fit([], [])

    def test_tied_inputs_share_one_fitted_value(self):
        # Tied x values must map to ONE fitted value (their mean). Without
        # tie-pooling, tied inputs with increasing y never violate PAVA and
        # receive different values -- inventing rank the source didn't state.
        xs = [3.0, 3.0, 1.0, 2.0]
        ys = [9.0, 7.0, 1.0, 5.0]
        fit_x, fit_y = isotonic_fit(xs, ys)
        p1 = isotonic_predict(fit_x, fit_y, 3.0)
        self.assertEqual(p1, 8.0)  # mean of the tied pair
        self.assertTrue(all(b >= a for a, b in zip(fit_y, fit_y[1:])),
                        "fitted values must stay non-decreasing")

    def test_tied_inputs_preserve_sum(self):
        # The fixed-pie invariant at the math level: fitted values must sum
        # to the anchor total. The unpooled-tie defect broke this.
        xs = [3.0, 3.0, 3.0, 1.0, 2.0, 2.0]
        ys = [9.0, 7.0, 8.0, 1.0, 5.0, 4.0]
        fit_x, fit_y = isotonic_fit(xs, ys)
        preds = [isotonic_predict(fit_x, fit_y, x) for x in xs]
        self.assertAlmostEqual(sum(preds), sum(ys), places=9)


class TestReindexStage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.players_path, self.players = make_players(self.tmp)

    def test_rank_order_preserved_within_position(self):
        players = self.players
        def anchor_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return {"QB": 5, "RB": 40, "WR": 30, "TE": 10}[pl["pos"]] + j
        def native_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return 100 + 3 * j  # different scale, same order
        fx = make_fixture(self.tmp, players, anchor_fn)
        cand = make_candidate(self.tmp, "syn", players, native_fn)
        section, review = run_stage(cand, fx, self.players_path)
        self.assertEqual(review, [])
        for pos in POS:
            slugs = [pl["name"].lower() for pl in players["players"] if pl["pos"] == pos]
            reidx = [section["combos"]["full_12"]["reindexed"][s] for s in slugs]
            self.assertTrue(all(b >= a for a, b in zip(reidx, reidx[1:])),
                            f"{pos}: reindexed order must follow native order")
            self.assertEqual(section["combos"]["full_12"]["n"][pos], 12)

    def test_positions_never_pooled(self):
        # QB native values are HUGE vs RB anchor scale; a pooled fit would
        # drag RB predictions up. Per-position fits must not cross-contaminate.
        players = self.players
        def anchor_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return {"QB": 5, "RB": 40, "WR": 30, "TE": 10}[pl["pos"]] + j
        def native_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return {"QB": 1000, "RB": 10, "WR": 10, "TE": 10}[pl["pos"]] + j
        fx = make_fixture(self.tmp, players, anchor_fn)
        cand = make_candidate(self.tmp, "syn", players, native_fn)
        section, _ = run_stage(cand, fx, self.players_path)
        rb_reidx = [section["combos"]["full_12"]["reindexed"][pl["name"].lower()]
                    for pl in players["players"] if pl["pos"] == "RB"]
        # RB anchor tops out at 51; a pooled fit with QB's 1000-scale natives
        # would predict far above it.
        self.assertLess(max(rb_reidx), 60,
                        "RB predictions must come from the RB fit only")

    def test_fewer_than_ten_pairs_fails_closed(self):
        tmp_players = {"meta": {}, "players": [
            {"name": f"Player QB{j}", "pos": "QB", "player_key": 2000 + j} for j in range(9)]}
        pp = self.tmp / "players9.json"
        pp.write_text(json.dumps(tmp_players))
        def anchor_fn(pl):
            return 5.0
        fx = make_fixture(self.tmp, tmp_players, anchor_fn)
        cand = make_candidate(self.tmp, "syn", tmp_players, lambda pl: 100.0)
        with self.assertRaises(SystemExit):
            run_stage(cand, fx, pp)

    def test_missing_anchor_combo_fails_closed(self):
        players = self.players
        fx = make_fixture(self.tmp, players, lambda pl: 5.0)
        cand = make_candidate(self.tmp, "syn", players, lambda pl: 100.0,
                              combos=("full_99",))
        with self.assertRaises(SystemExit):
            run_stage(cand, fx, self.players_path)

    def test_wrong_schema_fails_closed(self):
        bad = self.tmp / "bad.json"
        bad.write_text(json.dumps({"schema": "something-else"}))
        fx = make_fixture(self.tmp, self.players, lambda pl: 5.0)
        with self.assertRaises(SystemExit):
            rcs.reindex_section(str(bad), str(fx), str(self.players_path))

    def test_nulls_stay_absent_and_zeros_stay_zero(self):
        players = self.players
        def anchor_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return 0.0 if j in (0, 1) else 10.0 + j
        def native_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            if j == 11:
                return None  # null: absent from native
            return 0.0 if j in (0, 1) else 100.0 + j
        fx = make_fixture(self.tmp, players, anchor_fn)
        cand = make_candidate(self.tmp, "syn", players, native_fn)
        section, review = run_stage(cand, fx, self.players_path)
        rei = section["combos"]["full_12"]["reindexed"]
        for pos in POS:
            zero_slugs = [f"player {pos.lower()}{j}" for j in (0, 1)]
            null_slug = f"player {pos.lower()}11"
            for s in zero_slugs:
                self.assertIn(s, rei, "genuine zero must be carried")
                self.assertEqual(rei[s], 0.0, "genuine zero must stay zero")
            self.assertNotIn(null_slug, rei, "null must stay absent")
            self.assertEqual(section["combos"]["full_12"]["n"][pos], 11)

    def test_kdst_goes_to_review_not_indexed(self):
        players = {"meta": {}, "players": [
            {"name": f"Player {pos}{j}", "pos": pos, "player_key": 3000 + i * 100 + j}
            for i, pos in enumerate(("QB", "RB", "WR", "TE", "K", "DST"))
            for j in range(12)]}
        pp = self.tmp / "players_k.json"
        pp.write_text(json.dumps(players))
        fx = make_fixture(self.tmp, players, lambda pl: 5.0)
        cand = make_candidate(self.tmp, "syn", players, lambda pl: 100.0)
        section, review = run_stage(cand, fx, pp)
        rei = section["combos"]["full_12"]["reindexed"]
        kdst = [s for s in rei if s.startswith("player k") or s.startswith("player dst")]
        self.assertEqual(kdst, [], "K/DST must never be indexed")
        self.assertEqual(len([r for r in review if "not indexed" in r["reason"]]), 24)

    def test_fixed_pie_factor_math(self):
        players = self.players
        def anchor_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return 10.0 + j
        fx = make_fixture(self.tmp, players, anchor_fn)
        cand = make_candidate(self.tmp, "syn", players, lambda pl: 50.0)
        section, _ = run_stage(cand, fx, self.players_path)
        it = section["combos"]["full_12"]["index_total"]["RB"]
        self.assertAlmostEqual(it["factor"], it["target_total"] / it["pre_total"], places=5)
        self.assertEqual(it["n_priced"], 12)
        # every native maps to the same anchor-median-ish value; totals consistent
        self.assertGreater(it["pre_total"], 0)

    def test_stored_values_sum_to_target_total(self):
        # The fixed-pie invariant: the STORED reindexed values (not just the
        # recorded factor) must sum to target_total per position. Recording
        # the factor without applying it silently breaks the pie.
        players = self.players
        def anchor_fn(pl):
            j = int(''.join(c for c in pl["name"] if c.isdigit()))
            return 10.0 + j
        fx = make_fixture(self.tmp, players, anchor_fn)
        # Tied natives (real sources publish ties): exercises both the
        # tie-pooling in the PAVA fit and the fixed-pie factor application.
        cand = make_candidate(self.tmp, "syn", players,
                              lambda pl: 50.0 + (int(''.join(
                                  c for c in pl["name"] if c.isdigit())) // 2))
        section, _ = run_stage(cand, fx, self.players_path)
        combo = section["combos"]["full_12"]
        pos_of = {pl["name"].lower(): pl["pos"] for pl in players["players"]}
        totals = {}
        for slug, val in combo["reindexed"].items():
            totals[pos_of[slug]] = totals.get(pos_of[slug], 0.0) + val
        for pos, total in totals.items():
            target = combo["index_total"][pos]["target_total"]
            # 1-decimal rounding can drift at most 0.05 * n_priced
            slack = 0.05 * combo["index_total"][pos]["n_priced"] + 1e-9
            self.assertLessEqual(abs(total - target), slack,
                                 f"{pos}: stored sum {total} vs target {target}")

    def test_output_never_under_data(self):
        players = self.players
        fx = make_fixture(self.tmp, players, lambda pl: 5.0)
        cand = make_candidate(self.tmp, "syn", players, lambda pl: 100.0)
        with self.assertRaises(SystemExit):
            rcs.main([str(cand), "--out", str(rcs.REPO / "data" / "evil.json")])

    def test_candidate_input_not_mutated(self):
        players = self.players
        fx = make_fixture(self.tmp, players, lambda pl: 5.0)
        cand = make_candidate(self.tmp, "syn", players, lambda pl: 100.0)
        before = cand.read_text()
        run_stage(cand, fx, self.players_path)
        self.assertEqual(cand.read_text(), before)


class TestRealFixtureSmoke(unittest.TestCase):
    """Runs the stage against the real fixture pair; asserts internal
    consistency (not legacy equality -- the anchor moved to the ESPN leg)."""

    def test_usatoday_reindexes_clean(self):
        repo = Path(__file__).resolve().parent.parent
        fixture = repo / "data/fixtures/current/comparison-sources-data.json"
        players_p = repo / "data/fixtures/current/players.json"
        c = json.loads(fixture.read_text())
        # Build a candidate straight from the fixture's usatoday native values.
        tmp = Path(tempfile.mkdtemp())
        cand = {
            "schema": "trade-value-source-reference-v1",
            "source_key": "usatoday",
            "asof": "2026-09-19",
            "combos": {},
        }
        for combo_name, combo in c["sources"]["usatoday"]["combos"].items():
            keys = c.get("player_keys", {})
            cand["combos"][combo_name] = {
                "native": dict(combo["native"]),
                "player_keys": {s: keys.get(s) for s in combo["native"]},
            }
        cp = tmp / "usa-candidate.json"
        cp.write_text(json.dumps(cand))
        section, review = rcs.reindex_section(str(cp), str(fixture), str(players_p))
        self.assertEqual(section["reindex_status"], "complete")
        # Every combo's pie target == ESPN-leg total over the same priced set.
        espn = c["sources"]["espn"]["combos"]
        fkeys = c.get("player_keys", {})
        ppos = {p["player_key"]: p["pos"]
                for p in json.loads(players_p.read_text())["players"]}
        pos_by_slug = {s: ppos[k] for s, k in fkeys.items() if k in ppos}
        for combo_name, combo in section["combos"].items():
            anchor = espn[combo_name]["values"]
            for pos in POS:
                priced = [s for s in combo["reindexed"] if pos_by_slug.get(s) == pos]
                target = sum(anchor[s] for s in priced if s in anchor)
                self.assertAlmostEqual(
                    combo["index_total"][pos]["target_total"], round(target, 1),
                    places=0, msg=f"{combo_name}/{pos} pie target")
        # No review rows expected on the real pair (all slugs resolve).
        self.assertEqual(review, [])


class TestBuilderToReindexInterface(unittest.TestCase):
    """The candidate builder's output must be directly consumable by the
    reindex stage. Regression: the builder was reworked to emit
    trade-value-comparison-section-candidate-v1 while the reindex still
    demanded the legacy shape -- every real run died with
    "unsupported candidate schema". This test runs the REAL builder into
    the REAL reindex; it fails on the pre-fix code."""

    def test_builder_output_feeds_reindex(self):
        import build_comparison_source_section as bcss
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # Synthetic universe: 12 players x 4 positions.
            players_doc = {"players": []}
            rows = []
            pkey = 1000
            for i, pos in enumerate(POS):
                for j in range(12):
                    pkey += 1
                    name = f"iface {pos} {j}"
                    players_doc["players"].append(
                        {"player_key": pkey, "name": name.title(), "pos": pos})
                    rows.append({"player_key": pkey, "canonical_name": name.title(),
                                 "source_player_name": name.title(),
                                 "value": float(50 + j * 3 + i),
                                 "scoring": "full", "teams": 12})
            players_p = tmp / "players.json"
            players_p.write_text(json.dumps(players_doc))
            comparison = {"player_keys": {f"iface {pos} {j}": 1001 + i * 12 + j
                                          for i, pos in enumerate(POS)
                                          for j in range(12)}}
            comp_p = tmp / "comparison.json"
            comp_p.write_text(json.dumps(comparison))
            reference = {"schema": "trade-value-source-reference-v1",
                         "source": "iface-source", "fetched_at": "2026-09-21T00:00:00Z",
                         "rows": rows}
            ref_p = tmp / "reference.json"
            ref_p.write_text(json.dumps(reference))

            section = bcss.build_section(ref_p, comp_p, section_key="ifacesrc", meta={})
            # The reindex stage's contract: source_key + per-combo player_keys.
            self.assertIn("source_key", section)
            for combo in section["combos"].values():
                self.assertIn("player_keys", combo)
                self.assertEqual(set(combo["player_keys"]), set(combo["native"]))
            cand_p = tmp / "candidate.json"
            cand_p.write_text(json.dumps(section))

            # Synthetic ESPN anchor leg with distinct values per slug.
            combos = {"full_12": {"values": {
                f"iface {pos} {j}": float(40 + j * 2 + i)
                for i, pos in enumerate(POS) for j in range(12)}}}
            fx_p = tmp / "fixture.json"
            fx_p.write_text(json.dumps({"sources": {"espn": {"combos": combos}}}))

            section_out, review = rcs.reindex_section(str(cand_p), str(fx_p), str(players_p))
            self.assertEqual(section_out["reindex_status"], "complete")
            self.assertEqual(review, [])
            got = section_out["combos"]["full_12"]["reindexed"]
            self.assertEqual(len(got), 48)


class TestQBAnchorResolution(unittest.TestCase):
    """QB-suffixed combos (qb1/qb2 = leagues starting 1/2 QBs) anchor to
    their QB-stripped base combo on the ESPN leg, explicitly and recorded --
    never silently. Unknown combos still fail closed."""

    def test_exact_combo_still_preferred(self):
        anchor, mapping = rcs.resolve_anchor_combo("full_12", {"full_12": {}, "half_12": {}})
        self.assertEqual((anchor, mapping), ("full_12", "exact"))

    def test_qb_suffix_strips_to_base_anchor(self):
        anchor, mapping = rcs.resolve_anchor_combo("full_12_qb2", {"full_12": {}})
        self.assertEqual(anchor, "full_12")
        self.assertEqual(mapping, "qb_suffix_strip:full_12_qb2->full_12")

    def test_qb1_suffix_also_strips(self):
        anchor, mapping = rcs.resolve_anchor_combo("half_14_qb1", {"half_14": {}})
        self.assertEqual((anchor, mapping), ("half_14", "qb_suffix_strip:half_14_qb1->half_14"))

    def test_unknown_combo_still_refuses(self):
        # The fail-closed rule survives: no anchor, no guess.
        with self.assertRaises(SystemExit):
            rcs.resolve_anchor_combo("weird_99", {"full_12": {}})

    def test_qb3_suffix_does_not_strip(self):
        # Only qb1/qb2 are real league settings; qb3 must not resolve.
        with self.assertRaises(SystemExit):
            rcs.resolve_anchor_combo("full_12_qb3", {"full_12": {}})

    def test_qb_suffix_never_overrides_exact_anchor(self):
        # If the anchor ever gains a real full_12_qb2 combo, exact wins.
        anchor, mapping = rcs.resolve_anchor_combo(
            "full_12_qb2", {"full_12": {}, "full_12_qb2": {}})
        self.assertEqual((anchor, mapping), ("full_12_qb2", "exact"))

    def test_end_to_end_qb_combo_records_mapping(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # 12 QB + 12 RB so the per-position minimum is met.
            plist = {"players": []}
            key = 7000
            for pos in ("QB", "RB", "WR", "TE"):
                for j in range(12):
                    key += 1
                    plist["players"].append(
                        {"player_key": key, "name": f"Qb {pos} {j}".title(), "pos": pos})
            players_p = tmp / "players.json"
            players_p.write_text(json.dumps(plist))
            anchor_vals = {}
            for pl in plist["players"]:
                slug = pl["name"].lower()
                anchor_vals[slug] = 30.0 if pl["pos"] == "QB" else 50.0
            fx_p = tmp / "fixture.json"
            fx_p.write_text(json.dumps(
                {"sources": {"espn": {"combos": {"full_12": {"values": anchor_vals}}}}}))
            cand = make_candidate(tmp, "qbsrc", plist,
                                  lambda pl: 100.0, combos=("full_12_qb2",))
            section, review = rcs.reindex_section(str(cand), str(fx_p), str(players_p))
            self.assertEqual(section["reindex_status"], "complete")
            combo = section["combos"]["full_12_qb2"]
            self.assertEqual(combo["anchor_combo"], "full_12")
            self.assertEqual(combo["anchor_mapping"],
                             "qb_suffix_strip:full_12_qb2->full_12")
            self.assertEqual(review, [])


if __name__ == "__main__":
    unittest.main()
