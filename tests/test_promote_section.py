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


def write_import_health(path, source="fantasycalc", status="ok", vintage="Week 3",
                        failure_reason="__default__"):
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
                "failure_reason": (
                    (None if status == "ok" else "STALE_VINTAGE: old")
                    if failure_reason == "__default__" else failure_reason),
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

    def test_week_label_travels_with_promoted_values(self):
        """JEG-436: the chart reads `week_designated` before content_vintage.
        Promoting Week-3 natives over a section labelled "Week 2" must
        relabel it "Week 3" (the pre-fix promoter kept "Week 2": week-3
        values shown as Week 2)."""
        fx_path, rp, revp = ready_review(self.tmp, source="fantasycalc")
        fx = json.loads(fx_path.read_text())
        fx["sources"]["fantasycalc"]["week_designated"] = "Week 2"
        fx["sources"]["fantasycalc"]["content_vintage"] = "Week 2"
        fx_path.write_text(json.dumps(fx))
        doc = json.loads(rp.read_text())
        doc["content_vintage"] = "Week 3"
        doc["source_provenance"] = {"source": "fantasycalc", "content_vintage": "Week 3",
                                    "vintage_kind": "week_designated", "week_designated": 3}
        rp.write_text(json.dumps(doc))
        rev = json.loads(revp.read_text())
        rev["reindexed_sha256"] = promo.sha256_file(rp)
        revp.write_text(json.dumps(rev))
        health = self.tmp / "source-import-health.json"
        write_import_health(health, vintage="Week 3", status="ok")
        promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                      record_dir=str(self.records), import_health_path=str(health))
        after = json.loads(fx_path.read_text())["sources"]["fantasycalc"]
        self.assertEqual("Week 3", after["content_vintage"])
        self.assertEqual("Week 3", after["week_designated"])

    def _active_review(self, vintage="Week 3"):
        """Ready review for an active source; candidate vintage None = absent."""
        fx_path, rp, revp = ready_review(self.tmp, source="fantasycalc")
        doc = json.loads(rp.read_text())
        doc.pop("content_vintage", None)
        doc.pop("source_provenance", None)
        if vintage is not None:
            doc["content_vintage"] = vintage
            doc["source_provenance"] = {"source": "fantasycalc",
                                        "content_vintage": vintage}
        rp.write_text(json.dumps(doc))
        rev = json.loads(revp.read_text())
        rev["reindexed_sha256"] = promo.sha256_file(rp)
        revp.write_text(json.dumps(rev))
        return fx_path, revp

    def _promote_active(self, fx_path, revp, health):
        return promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                             record_dir=str(self.records),
                             import_health_path=str(health))

    def test_l1_gate_promotes_one_week_lag_under_its_own_vintage(self):
        """build-lag-001 (LAG-005): a LAGGING_ONE_WEEK warning promotes, and
        the promoted section keeps the source's own week label; a TABLE_DRIFT
        warning, a stale entry, or a candidate relabelled to another week is
        refused."""
        lag_reason = ("LAGGING_ONE_WEEK (non-blocking): fantasycalc content Week 3 "
                      "is one week behind current content Week 4")
        health = self.tmp / "health.json"

        fx_path, revp = self._active_review(vintage="Week 3")
        write_import_health(health, vintage="Week 3", status="warning",
                            failure_reason="TABLE_DRIFT: table latest vintage Week 4 "
                                           "!= manifest vintage Week 3")
        with self.assertRaises(SystemExit) as ctx:
            self._promote_active(fx_path, revp, health)
        self.assertIn("not 'ok' or a one-week lag", str(ctx.exception))

        write_import_health(health, vintage="Week 3", status="stale")
        with self.assertRaises(SystemExit):
            self._promote_active(fx_path, revp, health)

        # Candidate claims Week 4 while L1 holds Week 3: refused (no relabel).
        fx4, revp4 = self._active_review(vintage="Week 4")
        write_import_health(health, vintage="Week 3", status="warning",
                            failure_reason=lag_reason)
        with self.assertRaises(SystemExit) as ctx:
            self._promote_active(fx4, revp4, health)
        self.assertIn("does not match fresh L1 vintage", str(ctx.exception))

        fx_path, revp = self._active_review(vintage="Week 3")
        result = self._promote_active(fx_path, revp, health)
        after = json.loads(fx_path.read_text())["sources"]["fantasycalc"]
        self.assertEqual("Week 3", after["content_vintage"])
        rec = json.loads(Path(result["promotion_record"]).read_text())
        gate = rec["l1_import_health_gate"]
        self.assertEqual("warning", gate["status"])
        self.assertTrue(gate["failure_reason"].startswith("LAGGING_ONE_WEEK"))

    def test_l1_gate_refuses_when_import_health_file_missing(self):
        fx_path, revp = self._active_review()
        with self.assertRaises(SystemExit) as ctx:
            self._promote_active(fx_path, revp, self.tmp / "no-such-health.json")
        self.assertIn("missing or unreadable", str(ctx.exception))

    def test_l1_gate_refuses_wrong_health_schema(self):
        fx_path, revp = self._active_review()
        health = self.tmp / "health.json"
        write_import_health(health)
        doc = json.loads(health.read_text())
        doc["schema"] = "something-else-v1"
        health.write_text(json.dumps(doc))
        with self.assertRaises(SystemExit) as ctx:
            self._promote_active(fx_path, revp, health)
        self.assertIn("unsupported schema", str(ctx.exception))

    def test_l1_gate_refuses_when_source_has_no_health_entry(self):
        fx_path, revp = self._active_review()
        health = self.tmp / "health.json"
        write_import_health(health, source="usatoday")  # not fantasycalc
        with self.assertRaises(SystemExit) as ctx:
            self._promote_active(fx_path, revp, health)
        self.assertIn("no entry for 'fantasycalc'", str(ctx.exception))

    def test_l1_gate_refuses_candidate_without_content_vintage(self):
        fx_path, revp = self._active_review(vintage=None)
        health = self.tmp / "health.json"
        write_import_health(health, vintage="Week 3", status="ok")
        with self.assertRaises(SystemExit) as ctx:
            self._promote_active(fx_path, revp, health)
        self.assertIn("lacks immutable content_vintage", str(ctx.exception))

    def test_l1_gate_not_applied_to_non_active_source(self):
        fx_path, rp, revp = ready_review(self.tmp)  # source "syn"
        result = promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                               record_dir=str(self.records))
        rec = json.loads(Path(result["promotion_record"]).read_text())
        self.assertFalse(rec["l1_import_health_gate"]["applied"])


class MergePromotedComboTest(unittest.TestCase):
    """_merge_promoted_combo must carry the candidate's translation provenance.

    2026-10-03: promote() copied native/reindexed/fit/n/index_total but not
    the "translation" block stamped by translate_via_vorp.py, so the fixture
    kept a stale translation provenance (null week/season grain) while the
    fresh fit["vorp_translation"] carried the real one. The monitor's
    vorp_translation section warned "grain week not recorded" on fresh data.
    """

    def _combo(self, translation):
        combo = {
            "native": {"a": 100.0},
            "reindexed": {"a": 10.0},
            "fit": {"flex_aware_pie": {"method": "m"}},
            "n": {"qb": 1},
            "index_total": {},
        }
        if translation is not None:
            combo["translation"] = translation
        return combo

    def test_merge_carries_candidate_translation(self):
        # Discrimination: pre-fix merge drops the candidate's translation
        # block, so the promoted combo keeps the stale null-grain block.
        new_combo = self._combo({"method": "vorp-supabase",
                                 "grain": {"week": None, "season": None}})
        cand = self._combo({"method": "vorp-supabase",
                            "grain": {"week": 4, "season": 2026},
                            "n_translated": 176})
        promo._merge_promoted_combo(new_combo, cand)
        self.assertEqual(new_combo["translation"]["grain"]["week"], 4)
        self.assertEqual(new_combo["translation"]["grain"]["season"], 2026)
        self.assertEqual(new_combo["translation"]["n_translated"], 176)
        # Candidate mutation must not alias the fixture block.
        cand["translation"]["grain"]["week"] = 99
        self.assertEqual(new_combo["translation"]["grain"]["week"], 4)

    def test_merge_without_candidate_translation_keeps_existing(self):
        # Fail-closed: when the candidate carries no translation block the
        # existing fixture provenance is left untouched, never invented.
        existing = {"method": "vorp-supabase",
                    "grain": {"week": 3, "season": 2026}}
        new_combo = self._combo(existing)
        cand = self._combo(None)
        promo._merge_promoted_combo(new_combo, cand)
        self.assertEqual(new_combo["translation"], existing)

    def test_merge_still_copies_value_fields(self):
        new_combo = self._combo(None)
        cand = self._combo({"method": "reindex-fallback",
                            "grain": {"week": 4, "season": 2026}})
        cand["reindexed"] = {"a": 11.0}
        promo._merge_promoted_combo(new_combo, cand)
        self.assertEqual(new_combo["reindexed"], {"a": 11.0})
        self.assertEqual(new_combo["translation"]["method"], "reindex-fallback")


if __name__ == "__main__":
    unittest.main()
