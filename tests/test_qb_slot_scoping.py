"""Regression tests for QB-slot expansion scoping in build_comparison_source_section.

Background (2026-09-29): a change duplicated EVERY qb=None reference row into
qb1/qb2 variants, regardless of source. Only fantasycalc's fixture section uses
_qb1/_qb2 combos; cbs, espn, fantasypros, and usatoday use base combos. The
over-broad duplication made the four base-combo sources emit _qb1/_qb2 combos
their fixture sections do not expect, breaking candidate-vs-fixture matching.

The fix scopes the duplication: qb=None rows are split only when the fixture
expects QB-split combos for THAT source. These tests pin that behavior:

1. A qb-split source (fantasycalc) still gets qb=None rows split into qb1/qb2.
2. Rows that already carry qb=1/qb=2 are never re-duplicated.
3. Base-combo sources (cbs, espn, fantasypros, usatoday) keep qb=None rows as
   base combos -- no _qb1/_qb2 combos are emitted.
4. The split mapping is exact: one qb1 copy + one qb2 copy, values preserved.
"""

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reference_artifact(rows, source, review_rows=None):
    return {
        "schema": "trade-value-source-reference-v1",
        "generated_at": "2026-09-29T12:00:00Z",
        "input_match": f"output/source-matches/{source}/matched.json",
        "source": source,
        "fetched_at": "2026-09-29T12:00:00Z",
        "scoring": "ppr",
        "teams": 12,
        "rows": rows,
        "review_rows": review_rows or [],
    }


def fixture_with_combos(source, combos):
    """Minimal comparison fixture with the given combo names for one source."""
    return {
        "built_at": "2026-09-29T12:00:00Z",
        "display": {"josh allen": "Josh Allen"},
        "player_keys": {"josh allen": 869},
        "teams": {"josh allen": "BUF"},
        "sources": {
            source: {
                "name": source.title(),
                "combos": {combo: {"native": {}, "n": 0} for combo in combos},
            }
        },
    }


def ref_row(key, name, value, scoring="ppr", teams=12, qb=None):
    row = {"player_key": key, "canonical_name": name, "source_player_name": name,
           "value": value, "scoring": scoring, "teams": teams,
           "pos": "QB", "team": "BUF", "source_player_id": None}
    if qb is not None:
        row["qb"] = qb
    return row


class QbSlotScopingTest(unittest.TestCase):
    def build_section(self, tmp: Path, rows, source, fixture_combos):
        ref = tmp / "reference.json"
        fixture = tmp / "comparison.json"
        section = tmp / "section.json"
        write_json(ref, reference_artifact(rows, source))
        write_json(fixture, fixture_with_combos(source, fixture_combos))
        result = subprocess.run(
            ["python3", "pipelines/build_comparison_source_section.py",
             "--input", str(ref), "--comparison", str(fixture),
             "--output", str(section)],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(0, result.returncode,
                         msg=f"build_comparison_source_section failed:\n{result.stderr}")
        return json.loads(section.read_text(encoding="utf-8"))

    def test_qb_none_splits_for_qb_split_source(self):
        """fantasycalc (qb-split fixture): qb=None rows become qb1 + qb2."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0, qb=None)]
            section = self.build_section(
                tmp, rows, "fantasycalc", ["full_12_qb1", "full_12_qb2"])
            combos = section["combos"]
            self.assertEqual({"full_12_qb1", "full_12_qb2"}, set(combos))
            self.assertEqual({"josh allen": 24.0}, combos["full_12_qb1"]["native"])
            self.assertEqual({"josh allen": 24.0}, combos["full_12_qb2"]["native"])

    def test_qb_set_rows_not_reduplicated(self):
        """Rows already carrying qb=1/qb=2 pass through untouched."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0, qb=1),
                    ref_row(869, "Josh Allen", 22.0, qb=2)]
            section = self.build_section(
                tmp, rows, "fantasycalc", ["full_12_qb1", "full_12_qb2"])
            combos = section["combos"]
            self.assertEqual({"full_12_qb1", "full_12_qb2"}, set(combos))
            self.assertEqual({"josh allen": 24.0}, combos["full_12_qb1"]["native"])
            self.assertEqual({"josh allen": 22.0}, combos["full_12_qb2"]["native"])
            # No duplicate_player_key review rows: each (player, combo) unique.
            reasons = [r["reason"] for r in section["review_rows"]]
            self.assertNotIn("duplicate_player_key", reasons)

    def test_qb_none_stays_base_for_non_split_sources(self):
        """cbs/espn/fantasypros/usatoday: qb=None rows yield base combos only."""
        for source in ("cbs", "espn", "fantasypros", "usatoday"):
            with TemporaryDirectory() as tmp:
                tmp = Path(tmp)
                rows = [ref_row(869, "Josh Allen", 24.0, qb=None)]
                section = self.build_section(tmp, rows, source, ["full_12"])
                combos = section["combos"]
                self.assertEqual({"full_12"}, set(combos),
                                 msg=f"{source} emitted unexpected qb-split combos")
                self.assertEqual({"josh allen": 24.0}, combos["full_12"]["native"])

    def test_split_mapping_preserves_values_exactly(self):
        """The qb1 and qb2 copies carry the identical native value."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 37.5, scoring="half_ppr", qb=None)]
            section = self.build_section(
                tmp, rows, "fantasycalc", ["half_12_qb1", "half_12_qb2"])
            combos = section["combos"]
            self.assertEqual(37.5, combos["half_12_qb1"]["native"]["josh allen"])
            self.assertEqual(37.5, combos["half_12_qb2"]["native"]["josh allen"])
            # Exactly two placements for one input row (one per qb slot).
            # reference_row_count is measured post-expansion.
            self.assertEqual(2, section["summary"]["placed_count"])
            self.assertEqual(2, section["summary"]["reference_row_count"])

    def test_mixed_qb_rows_for_split_source(self):
        """qb=None splits while qb-set rows pass through, in one section."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0, qb=None),   # splits
                    ref_row(869, "Josh Allen", 30.0, qb=1)]       # stays
            section = self.build_section(
                tmp, rows, "fantasycalc", ["full_12_qb1", "full_12_qb2"])
            combos = section["combos"]
            # qb=None row -> qb1 copy; explicit qb=1 row collides on (player, combo)
            # and goes to review as a duplicate (fail-closed, never merged).
            reasons = [r["reason"] for r in section["review_rows"]]
            self.assertIn("duplicate_player_key", reasons)
            # The first-seen (split copy) wins; the explicit row is reviewed.
            self.assertEqual({"josh allen": 24.0}, combos["full_12_qb1"]["native"])
            self.assertEqual({"josh allen": 24.0}, combos["full_12_qb2"]["native"])

    def test_qb1_only_fixture_emits_no_qb2(self):
        """JEG-436: league-settings-001 / #361 retired FantasyCalc's qb2 blocks.
        A 12-team 1-QB snapshot against a qb1-only fixture must emit qb1 only;
        the old split minted `full_12_qb2` and the review held it as an
        unknown combo (2026-10-07 13:33Z chain)."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0, scoring=s, qb=None)
                    for s in ("ppr", "half_ppr", "standard")]
            section = self.build_section(
                tmp, rows, "fantasycalc",
                ["full_12_qb1", "half_12_qb1", "standard_12_qb1"])
            self.assertEqual({"full_12_qb1", "half_12_qb1", "standard_12_qb1"},
                             set(section["combos"]))

    def test_base_absent_from_fixture_falls_back_to_qb1(self):
        """A (scoring, teams) the fixture has no QB-split combo for gets qb1
        only (the importer pulls 1-QB values), never a minted qb2."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0, teams=10, qb=None)]
            section = self.build_section(tmp, rows, "fantasycalc", ["full_12_qb1"])
            self.assertEqual({"full_10_qb1"}, set(section["combos"]))

    def test_no_split_when_fixture_section_missing(self):
        """Unknown source (no fixture section): qb=None rows stay base."""
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rows = [ref_row(869, "Josh Allen", 24.0, qb=None)]
            section = self.build_section(tmp, rows, "newsource", ["full_12"])
            # Fixture has no "newsource" section -> no qb-split expectation.
            combos = section["combos"]
            self.assertEqual({"full_12"}, set(combos))


if __name__ == "__main__":
    unittest.main()
