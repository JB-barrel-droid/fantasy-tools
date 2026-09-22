"""Tests for the promotion-review stage.

Every audit is negative-tested against its named defect. Hermetic synthetic
fixtures, plus one real-fixture run (usatoday demo) asserting the review
reaches 'ready' with the anchor change disclosed.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))
import review_comparison_candidate as rvw  # noqa: E402

POS = ("QB", "RB", "WR", "TE")


def build(tmp, source="syn", per_pos=12, mutate=None, drop_pos=None,
          review_rows=(), reindex_status="complete", combos=("full_12",),
          fixture_combos=("full_12",)):
    """Build a matching (reindexed candidate, fixture) pair.

    mutate: fn(native_dict) applied to the candidate's natives (drift).
    drop_pos: position whose candidate priced set is halved (coverage drop).
    """
    players = {"meta": {}, "players": []}
    for i, pos in enumerate(POS):
        for j in range(per_pos):
            players["players"].append(
                {"name": f"Player {pos}{j}", "pos": pos,
                 "player_key": 5000 + i * 100 + j})
    pos_of = {f"player {p.lower()}{j}": p
              for p in POS for j in range(per_pos)}

    def natives():
        d = {}
        for p in POS:
            for j in range(per_pos):
                d[f"player {p.lower()}{j}"] = 100.0 + j
        return d

    fx_combos = {}
    for combo in fixture_combos:
        nat = natives()
        fx_combos[combo] = {
            "native": dict(nat),
            "reindexed": {s: v / 10.0 for s, v in nat.items()},
            "n": {p: per_pos for p in POS},
            "index_total": {p: {"target_total": 100.0, "pre_total": 105.0,
                                "factor": 0.952381, "n_priced": per_pos}
                            for p in POS},
        }
    fx = {"sources": {source: {"combos": fx_combos}},
          "player_keys": {f"player {p.lower()}{j}": 5000 + i * 100 + j
                          for i, p in enumerate(POS) for j in range(per_pos)}}
    fx_path = tmp / "fixture.json"
    fx_path.write_text(json.dumps(fx))

    cand_combos = {}
    for combo in combos:
        nat = natives()
        if mutate:
            nat = mutate(dict(nat))
        priced = {p: per_pos for p in POS}
        if drop_pos:
            keep = [s for s in nat if not s.startswith(f"player {drop_pos.lower()}")]
            half = [s for s in nat if s.startswith(f"player {drop_pos.lower()}")][:per_pos // 2]
            nat = {s: nat[s] for s in keep + half}
            priced[drop_pos] = per_pos // 2
        cand_combos[combo] = {
            "native": nat,
            "reindexed": {s: v / 9.0 for s, v in nat.items()},
            "fit": {p: {"method": "isotonic_pava"} for p in POS},
            "n": priced,
            "player_keys": {f"player {p.lower()}{j}": 5000 + i * 100 + j
                            for i, p in enumerate(POS) for j in range(per_pos)},
            "index_total": {p: {"target_total": 100.0, "pre_total": 110.0,
                                "factor": 0.909091, "n_priced": priced[p]}
                            for p in POS},
        }
    cand = {"schema": "trade-value-comparison-section-reindexed-v1",
            "source_key": source, "stage": "reference_compute",
            "reindex_status": reindex_status, "asof": "2026-09-21",
            "combos": cand_combos,
            "review_rows": list(review_rows)}
    cand_path = tmp / "cand.json"
    cand_path.write_text(json.dumps(cand))
    return cand_path, fx_path


def statuses(report):
    return {c["name"]: c["status"] for c in report["checks"]}


class TestReviewStage(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_ready_when_clean(self):
        cand, fx = build(self.tmp)
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        self.assertEqual(report["verdict"], "ready")
        self.assertNotIn("fail", statuses(report).values())

    def test_hold_on_untriaged_review_rows_then_ready(self):
        rows = ({"player_key": 1, "slug": "some guy", "combo": "full_12",
                 "reason": "position K not indexed -- skipped"},)
        cand, fx = build(self.tmp, review_rows=rows)
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(statuses(report)["review_rows_triaged"], "fail")
        # triage file clears it
        tri = self.tmp / "triage.json"
        tri.write_text(json.dumps({"some guy": "K, correctly excluded"}))
        report2 = rvw.review_candidate(str(cand), str(tri), str(fx))
        self.assertEqual(report2["verdict"], "ready")

    def test_hold_on_native_drift(self):
        def mutate(nat):
            for i, s in enumerate(list(nat)):
                if i % 10 == 0:  # 10% of values move
                    nat[s] += 5.0
            return nat
        cand, fx = build(self.tmp, mutate=mutate)
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(statuses(report)["native_drift:full_12"], "fail")

    def test_hold_on_coverage_drop(self):
        cand, fx = build(self.tmp, drop_pos="RB")
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(statuses(report)["coverage:full_12/RB"], "fail")

    def test_hold_on_missing_combo(self):
        cand, fx = build(self.tmp, combos=("full_12",),
                         fixture_combos=("full_12", "half_12"))
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(statuses(report)["combos_match"], "fail")

    def test_anchor_disclosure_always_present(self):
        cand, fx = build(self.tmp)
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        disc = [c for c in report["checks"] if c["name"] == "anchor_disclosure"]
        self.assertEqual(len(disc), 1)
        self.assertEqual(disc[0]["status"], "info")
        self.assertIn("ESPN leg", disc[0]["detail"])
        self.assertIn("Monday rail", disc[0]["detail"])

    def test_refuses_unfinished_reindex(self):
        cand, fx = build(self.tmp, reindex_status="pending")
        with self.assertRaises(SystemExit):
            rvw.review_candidate(str(cand), fixture_path=str(fx))

    def test_refuses_data_output(self):
        cand, fx = build(self.tmp)
        with self.assertRaises(SystemExit):
            rvw.main([str(cand), "--out", str(rvw.REPO / "data" / "evil.json")])

    def test_new_source_has_no_baseline(self):
        cand, _ = build(self.tmp, source="brand_new")
        fx_path = self.tmp / "fx2.json"
        fx_path.write_text(json.dumps({
            "sources": {},
            "player_keys": {f"player {p.lower()}{j}": 5000 + i * 100 + j
                            for i, p in enumerate(POS) for j in range(12)},
        }))
        report = rvw.review_candidate(str(cand), fixture_path=str(fx_path))
        self.assertEqual(report["verdict"], "ready")
        self.assertEqual(statuses(report)["baseline"], "info")

    def test_insane_factor_fails(self):
        cand, fx = build(self.tmp)
        doc = json.loads(cand.read_text())
        doc["combos"]["full_12"]["index_total"]["QB"]["factor"] = 42.0
        cand.write_text(json.dumps(doc))
        report = rvw.review_candidate(str(cand), fixture_path=str(fx))
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(statuses(report)["pie_factors_sane"], "fail")


class TestRealFixtureReview(unittest.TestCase):
    def test_usatoday_demo_reaches_ready(self):
        import reindex_comparison_section as rcs
        repo = Path(__file__).resolve().parent.parent
        fixture = repo / "data/fixtures/current/comparison-sources-data.json"
        players_p = repo / "data/fixtures/current/players.json"
        c = json.loads(fixture.read_text())
        fkeys = c.get("player_keys", {})
        # Build the candidate from the fixture's own usatoday natives, then
        # run the real stage-2 reindex on it -- fully hermetic, no local
        # output/ artifacts required (CI starts with a clean checkout).
        tmp = Path(tempfile.mkdtemp())
        cand = {"schema": "trade-value-source-reference-v1",
                "source_key": "usatoday", "asof": "2026-09-19",
                "reindex_status": "pending", "combos": {}}
        for combo_name, combo in c["sources"]["usatoday"]["combos"].items():
            cand["combos"][combo_name] = {
                "native": dict(combo["native"]),
                "player_keys": {s: fkeys.get(s) for s in combo["native"]},
            }
        cp = tmp / "usa-candidate.json"
        cp.write_text(json.dumps(cand))
        section, review_rows = rcs.reindex_section(str(cp), str(fixture), str(players_p))
        self.assertEqual(review_rows, [])
        rp = tmp / "usa-reindexed.json"
        rp.write_text(json.dumps(section))
        report = rvw.review_candidate(str(rp), fixture_path=str(fixture),
                                      players_path=str(players_p))
        # The demo candidate was built FROM the fixture natives: no drift,
        # no coverage change, no review rows -> ready, with the anchor
        # change disclosed and divergence measured.
        self.assertEqual(report["verdict"], "ready", json.dumps(
            [c for c in report["checks"] if c["status"] == "fail"], indent=1))
        disc = [c for c in report["checks"] if c["name"] == "anchor_disclosure"][0]
        self.assertIn("ESPN leg", disc["detail"])
        div = report["combos"]["full_12"]["anchor_divergence"]
        self.assertTrue(all(div[p]["n"] > 0 for p in POS))
        print("usatoday anchor divergence (ESPN leg vs Monday rail):",
              {p: div[p]["mean_abs"] for p in POS})


if __name__ == "__main__":
    unittest.main()
