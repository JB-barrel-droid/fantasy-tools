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


def build_world(tmp):
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
    fx = {"sources": {"syn": fx_section}, "player_keys": fkeys}
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
            "source_key": "syn", "asof": "2026-09-21",
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


def ready_review(tmp):
    """Run the real stage-2 reindex + stage-3 review; return review path."""
    import reindex_comparison_section as rcs
    fx_path, players_path, cp = build_world(tmp)
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


class TestPromote(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.records = self.tmp / "records"

    def test_happy_path(self):
        fx_path, rp, revp = ready_review(self.tmp)
        before = json.loads(fx_path.read_text())["sources"]["syn"]
        result = promo.promote(str(revp), APPROVE, fixture_path=str(fx_path),
                               record_dir=str(self.records))
        after = json.loads(fx_path.read_text())["sources"]["syn"]
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


if __name__ == "__main__":
    unittest.main()
