"""Tests for the promotion stage (the ONLY stage allowed to write under data/).

Every refusal is negative-tested against its named defect. All fixture writes
go to tmp dirs; the real fixture is never touched by tests.
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))
import promote_comparison_section as promo  # noqa: E402
import review_comparison_candidate as rvw  # noqa: E402

POS = ("QB", "RB", "WR", "TE")
APPROVE = "Test 2026-09-21 promote in test"


def build_world(tmp, source="syn"):
    """Synthetic (fixture, candidate) pair in the real fixture's shape."""
    players = []
    fkeys = {}
    for i, pos in enumerate(POS):
        for j in range(12):
            key = 5000 + i * 100 + j
            slug = f"player {pos.lower()}{j}"
            players.append({"name": f"Player {pos}{j}", "pos": pos,
                            "player_key": key})
            fkeys[slug] = key
    fx_section = {
        "name": "Syn", "kind": "test", "fetched_at": "2026-09-19",
        "combos": {},
    }
    for combo in ("full_12",):
        native = {f"player {p.lower()}{j}": 100.0 + j
                  for p in POS for j in range(12)}
        fx_section["combos"][combo] = {
            "native": dict(native),
            "reindexed": {s: v / 10.0 for s, v in native.items()},
            "fit": {"fit_n": 48, "anchor": "monday_rail"},
            "n": 48,
            "index_total": {p: {"target_total": 100.0, "n_priced": 12}
                            for p in POS},
        }
    fx = {"built_at": "2026-09-19T00:00:00Z",
          "sources": {source: fx_section}, "player_keys": fkeys}
    # The reindex stage anchors to the fixture's ESPN leg.
    anchor_values = {f"player {p.lower()}{j}": 60.0 - j
                     for p in POS for j in range(12)}
    fx["sources"]["espn"] = {"combos": {
        "full_12": {"values": anchor_values}}}
    fx_path = tmp / "fixture.json"
    fx_path.write_text(json.dumps(fx, separators=(",", ":")))
    players_path = tmp / "players.json"
    players_path.write_text(json.dumps({"players": players}))

    cand = {"schema": "trade-value-source-reference-v1",
            "source_key": source, "asof": "2026-09-21",
            "reindex_status": "pending", "combos": {}}
    for combo in ("full_12",):
        native = dict(fx_section["combos"][combo]["native"])
        cand["combos"][combo] = {
            "native": native,
            "player_keys": {s: fkeys[s] for s in native},
        }
    cp = tmp / "cand.json"
    cp.write_text(json.dumps(cand))
    return fx_path, players_path, cp


def ready_review(tmp, source="syn"):
    """Run the real stage-2 reindex + stage-3 review; return review path."""
    import reindex_comparison_section as rcs
    fx_path, players_path, cp = build_world(tmp, source=source)
    section, rows = rcs.reindex_section(str(cp), str(fx_path), str(players_path))
    assert rows == []
    rp = tmp / "reindexed.json"
    rp.write_text(json.dumps(section))
    report = rvw.review_candidate(str(rp), fixture_path=str(fx_path),
                                  players_path=str(players_path))
    assert report["verdict"] == "ready", report["checks"]
    revp = tmp / "review.json"
    revp.write_text(json.dumps(report))
    return fx_path, rp, revp


def write_import_health(path, source="fantasycalc", status="ok", vintage="Week 3"):
    payload = {
        "schema": "trade-value-import-health-v1",
        "checked_at": "2026-09-21T12:30:00Z",
        "nfl_week": 3,
        "sources": {
            source: {
                "status": status,
                "last_successful_import": "2026-09-21T12:30:00Z",
                "content_vintage": vintage,
                "vintage_kind": "week_designated",
                "row_count": 48,
                "supabase_table": "public.source_trade_values",
                "supabase_landing": True,
                "snapshot_path": "data/raw/sources/fantasycalc/week-3/snapshot.json",
                "failure_reason": None if status == "ok" else "STALE_VINTAGE: old",
            }
        },
    }
    path.write_text(json.dumps(payload))


class TestPromote(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.records = self.tmp / "records"

    def test_happy_path(self):
        fx_path, rp, revp = ready_review(self.tmp)
        before_fixture = json.loads(fx_path.read_text())
        before = before_fixture["sources"]["syn"]
        result = promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                               record_dir=str(self.records))
        after_fixture = json.loads(fx_path.read_text())
        after = after_fixture["sources"]["syn"]
        # reindexed math replaced
        self.assertNotEqual(before["combos"]["full_12"]["reindexed"],
                            after["combos"]["full_12"]["reindexed"])
        # natives byte-identical, vintage untouched
        self.assertEqual(before["combos"]["full_12"]["native"],
                         after["combos"]["full_12"]["native"])
        self.assertEqual(after["fetched_at"], "2026-09-19")
        # anchor recorded
        self.assertEqual(after["reindex_anchor"], "espn_leg")
        self.assertIn("monday rail", after["promotion_note"].lower())
        # built_at must be refreshed: promotion is a fixture write event
        self.assertIn("built_at", after_fixture)
        self.assertNotEqual(after_fixture["built_at"], before_fixture["built_at"],
                            "promotion must update fixture built_at so the freshness gate sees today")
        # promotion record with rollback + approver
        rec = json.loads(Path(result["promotion_record"]).read_text())
        self.assertEqual(rec["approved_by"], APPROVE)
        self.assertEqual(rec["replaced_section"], before)
        self.assertEqual(rec["anchor_change"], "monday_rail -> espn_leg")
        # fixture serialization preserved (compact, no trailing newline)
        raw = fx_path.read_text()
        self.assertFalse(raw.endswith("\n"))
        self.assertEqual(json.dumps(json.loads(raw), separators=(",", ":")), raw)

    def test_refuse_hold_verdict(self):
        fx_path, rp, revp = ready_review(self.tmp)
        rev = json.loads(revp.read_text())
        rev["verdict"] = "hold"
        revp.write_text(json.dumps(rev))
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_refuse_without_approve(self):
        fx_path, rp, revp = ready_review(self.tmp)
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), "", fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_refuse_reindexed_changed_since_review(self):
        fx_path, rp, revp = ready_review(self.tmp)
        doc = json.loads(rp.read_text())
        doc["combos"]["full_12"]["reindexed"]["player qb0"] += 1.0
        rp.write_text(json.dumps(doc))
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_refuse_fixture_drift_since_review(self):
        fx_path, rp, revp = ready_review(self.tmp)
        fx = json.loads(fx_path.read_text())
        fx["sources"]["syn"]["combos"]["full_12"]["native"]["player qb0"] += 1.0
        fx_path.write_text(json.dumps(fx, separators=(",", ":")))
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_refuse_unknown_slug(self):
        fx_path, rp, revp = ready_review(self.tmp)
        # Simulate a tampered artifact: candidate gains a slug the fixture
        # never heard of (the real reindex stage is fail-closed, so this can
        # only arrive via tampering).
        doc = json.loads(rp.read_text())
        doc["combos"]["full_12"]["native"]["mystery man"] = 50.0
        doc["combos"]["full_12"]["reindexed"]["mystery man"] = 5.0
        rp.write_text(json.dumps(doc))
        report = rvw.review_candidate(str(rp), fixture_path=str(fx_path),
                                      players_path=str(self.tmp / "players.json"))
        # the review fails closed first...
        self.assertEqual(report["verdict"], "hold")
        self.assertEqual(
            [c for c in report["checks"]
             if c["name"] == "identity_closure"][0]["status"], "fail")
        # ...and even a hand-flipped 'ready' cannot slip past promotion
        report["verdict"] = "ready"
        revp.write_text(json.dumps(report))
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_refuse_review_without_hashes(self):
        fx_path, rp, revp = ready_review(self.tmp)
        rev = json.loads(revp.read_text())
        del rev["reindexed_sha256"]
        revp.write_text(json.dumps(rev))
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_refuse_wrong_schema(self):
        fx_path, rp, revp = ready_review(self.tmp)
        rev = json.loads(revp.read_text())
        rev["schema"] = "something-else-v1"
        revp.write_text(json.dumps(rev))
        with self.assertRaises(SystemExit):
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records))

    def test_active_source_promotion_requires_fresh_matching_l1_vintage(self):
        fx_path, rp, revp = ready_review(self.tmp, source="fantasycalc")
        doc = json.loads(rp.read_text())
        doc["content_vintage"] = "Week 3"
        doc["source_provenance"] = {
            "source": "fantasycalc",
            "content_vintage": "Week 3",
            "vintage_kind": "week_designated",
            "week_designated": 3,
            "source_pulled_at": "2026-09-21T12:00:00Z",
            "snapshot_fetched_at": "2026-09-21T12:00:00Z",
        }
        rp.write_text(json.dumps(doc))
        rev = json.loads(revp.read_text())
        rev["reindexed_sha256"] = promo.sha256_file(rp)
        revp.write_text(json.dumps(rev))

        health = self.tmp / "source-import-health.json"
        write_import_health(health, vintage="Week 2")
        with self.assertRaises(SystemExit) as ctx:
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records), import_health_path=str(health))
        self.assertIn("does not match fresh L1 vintage", str(ctx.exception))

        write_import_health(health, vintage="Week 3", status="stale")
        with self.assertRaises(SystemExit) as ctx:
            promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                          record_dir=str(self.records), import_health_path=str(health))
        self.assertIn("not 'ok'", str(ctx.exception))

        write_import_health(health, vintage="Week 3", status="ok")
        result = promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                               record_dir=str(self.records), import_health_path=str(health))
        after = json.loads(fx_path.read_text())["sources"]["fantasycalc"]
        self.assertEqual("Week 3", after["content_vintage"])
        self.assertEqual("Week 3", after["source_provenance"]["content_vintage"])
        rec = json.loads(Path(result["promotion_record"]).read_text())
        self.assertEqual("Week 3", rec["l1_import_health_gate"]["content_vintage"])


class TestCoverageTriage(unittest.TestCase):
    """Coverage triage in review_comparison_candidate: the coverage_triage section
    of the triage JSON converts a specific coverage fail to info so the verdict
    can be 'ready' for genuine source movement.  Untriaged regressions still fail.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _make_review_with_coverage_drop(self):
        """Return a reindexed artifact whose half_12/RB count is 1 below the fixture."""
        import reindex_comparison_section as rcs
        import review_comparison_candidate as rvw_mod

        fx_path, players_path, cp = build_world(self.tmp, source="syn2")
        # Shrink the candidate so it has fewer RBs than the fixture
        section = json.loads(cp.read_text())
        # Remove one RB native entry to simulate coverage drop
        h12_native = section["combos"]["full_12"]["native"]
        rb_entries = [k for k in h12_native if " rb" in k]
        del h12_native[rb_entries[0]]
        # Also remove from player_keys so reindex sees the reduced set
        section["combos"]["full_12"]["player_keys"].pop(rb_entries[0], None)
        cp.write_text(json.dumps(section))

        section_doc, rows = rcs.reindex_section(str(cp), str(fx_path), str(players_path))
        rp = self.tmp / "reindexed2.json"
        rp.write_text(json.dumps(section_doc))
        return rp, fx_path, players_path, rvw_mod

    def test_untriaged_coverage_regression_is_hold(self):
        """Negative test: coverage reduction without triage must be 'hold'."""
        rp, fx_path, players_path, rvw_mod = self._make_review_with_coverage_drop()
        report = rvw_mod.review_candidate(str(rp), fixture_path=str(fx_path),
                                          players_path=str(players_path))
        self.assertEqual("hold", report["verdict"])
        coverage_fails = [c for c in report["checks"]
                          if c["name"].startswith("coverage:") and c["status"] == "fail"]
        self.assertTrue(coverage_fails, "expect at least one coverage fail")

    def test_triaged_coverage_regression_is_ready(self):
        """Positive test: documented coverage triage converts fail to info, verdict ready."""
        rp, fx_path, players_path, rvw_mod = self._make_review_with_coverage_drop()
        triage = self.tmp / "coverage-triage.json"
        triage.write_text(json.dumps({
            "coverage_triage": {
                "full_12/RB": "Week 4: player dropped from source chart (verified waived)"
            }
        }))
        report = rvw_mod.review_candidate(str(rp), triage_path=str(triage),
                                          fixture_path=str(fx_path),
                                          players_path=str(players_path))
        self.assertEqual("ready", report["verdict"],
                         f"checks: {[c for c in report['checks'] if c['status']=='fail']}")
        coverage_infos = [c for c in report["checks"]
                          if c["name"].startswith("coverage:") and c["status"] == "info"]
        self.assertTrue(coverage_infos, "triaged coverage should appear as info")
        self.assertIn("triaged coverage reduction", coverage_infos[0]["detail"])

    def test_other_combo_not_triaged_still_fails(self):
        """A triage entry for one pos does not mask a different untriaged regression."""
        rp, fx_path, players_path, rvw_mod = self._make_review_with_coverage_drop()
        # Only triage WR (which has no regression in our synthetic data); RB should still fail
        triage = self.tmp / "partial-triage.json"
        triage.write_text(json.dumps({
            "coverage_triage": {
                "full_12/WR": "Week 4: documented WR drop"
            }
        }))
        report = rvw_mod.review_candidate(str(rp), triage_path=str(triage),
                                          fixture_path=str(fx_path),
                                          players_path=str(players_path))
        self.assertEqual("hold", report["verdict"])
        rb_fails = [c for c in report["checks"]
                    if c["name"] == "coverage:full_12/RB" and c["status"] == "fail"]
        self.assertTrue(rb_fails, "RB coverage regression must remain a fail without triage")


if __name__ == "__main__":
    unittest.main()
