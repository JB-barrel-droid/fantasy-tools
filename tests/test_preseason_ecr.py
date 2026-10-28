"""JEG-1161: unit tests for pipelines/lib/preseason_ecr.py.

Tests only -- the module under test is not modified. Identity resolution is
stubbed with unittest.mock so the tests never touch the live players table
(no network, no clock): the draft source and the registry are the only inputs
and both are supplied here.

Discrimination (mutation check, see docs/claude-log/2026-10-27-preseason-ecr-tests.md):
flipping `min` -> `max` on the collision branch of load_preseason_ecr_ranks
turns test_collision_keeps_lowest_rank red; reverting turns it green.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "pipelines", "lib"))

import preseason_ecr  # noqa: E402
from preseason_ecr import (  # noqa: E402
    FIELD,
    SKILL_POSITIONS,
    annotate_rows,
    load_preseason_ecr_ranks,
    provenance_note,
)


def _write_draft(entries):
    """Write a draft JSON (norm-name -> entry) to a temp file; return path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as f:
        json.dump(entries, f)
    return path


class PreseasonEcrTestCase(unittest.TestCase):
    def setUp(self):
        self._paths = []
        # A truthy stub registry: load_preseason_ecr_ranks short-circuits on
        # `registry or load_registry()`, so the live table is never read.
        self.registry = object()

    def tearDown(self):
        for p in self._paths:
            try:
                os.remove(p)
            except OSError:
                pass

    def _draft(self, entries):
        path = _write_draft(entries)
        self._paths.append(path)
        return path

    def _load(self, entries, name_to_key):
        """Run the loader with resolve() stubbed by an explicit name->key map."""
        path = self._draft(entries)

        def fake_resolve(name, position=None, registry=None, **kw):
            return name_to_key.get(name)

        with mock.patch.object(preseason_ecr, "resolve", side_effect=fake_resolve):
            return load_preseason_ecr_ranks(registry=self.registry, draft_path=path)


class TestLoadRanks(PreseasonEcrTestCase):
    def test_non_skill_positions_skipped(self):
        # K and DST are dropped before the rank check; the skill rows survive.
        entries = {
            "kicker one": {"pos": "K", "rank_ecr": 1, "name": "Kicker One"},
            "dst one": {"pos": "DST", "rank_ecr": 2, "name": "Dst One"},
            "qb one": {"pos": "QB", "rank_ecr": 3, "name": "Qb One"},
        }
        ranks, report = self._load(entries, {"Qb One": 100})
        self.assertEqual(ranks, {100: 3})
        self.assertEqual(report["draft_entries"], 3)
        self.assertEqual(report["skill_entries"], 1)   # only the QB row
        self.assertEqual(report["resolved"], 1)
        self.assertEqual(report["unmatched"], 0)
        self.assertEqual(report["bad_ranks"], 0)
        self.assertEqual(report["collisions"], 0)

    def test_skill_positions_is_upper_case_only(self):
        # pos is upper()'d before the membership test: lower "qb" still counts.
        entries = {"qb one": {"pos": "qb", "rank_ecr": 4, "name": "Qb One"}}
        ranks, report = self._load(entries, {"Qb One": 100})
        self.assertEqual(ranks, {100: 4})
        self.assertEqual(report["skill_entries"], 1)

    def test_bad_ranks_counted_and_skipped(self):
        # 0, negative, True (bool), "3" (str) and missing all fail the
        # `isinstance(rank, int) and not bool and rank >= 1` gate.
        entries = {
            "zero": {"pos": "RB", "rank_ecr": 0, "name": "Zero"},
            "negative": {"pos": "RB", "rank_ecr": -5, "name": "Negative"},
            "bool": {"pos": "RB", "rank_ecr": True, "name": "Bool"},
            "string": {"pos": "RB", "rank_ecr": "3", "name": "String"},
            "missing": {"pos": "RB", "name": "Missing"},
            "good": {"pos": "RB", "rank_ecr": 7, "name": "Good"},
        }
        ranks, report = self._load(entries, {
            "Zero": 1, "Negative": 2, "Bool": 3, "String": 4,
            "Missing": 5, "Good": 6,
        })
        # Only the well-formed rank survives; nothing was resolved for the rest.
        self.assertEqual(ranks, {6: 7})
        self.assertEqual(report["bad_ranks"], 5)
        self.assertEqual(report["resolved"], 1)
        self.assertEqual(report["unmatched"], 0)
        self.assertEqual(report["skill_entries"], 6)

    def test_bad_rank_checked_before_resolution(self):
        # A bad rank with an unmatched name counts as bad_ranks only, not
        # unmatched: the rank gate runs before resolve().
        entries = {"x": {"pos": "WR", "rank_ecr": 0, "name": "Nobody"}}
        ranks, report = self._load(entries, {})  # name resolves to nothing
        self.assertEqual(ranks, {})
        self.assertEqual(report["bad_ranks"], 1)
        self.assertEqual(report["unmatched"], 0)

    def test_unmatched_names_counted_and_skipped(self):
        entries = {
            "known": {"pos": "TE", "rank_ecr": 5, "name": "Known"},
            "unknown": {"pos": "TE", "rank_ecr": 9, "name": "Unknown"},
        }
        ranks, report = self._load(entries, {"Known": 500})  # "Unknown" -> None
        self.assertEqual(ranks, {500: 5})
        self.assertEqual(report["unmatched"], 1)
        self.assertEqual(report["resolved"], 1)

    def test_collision_keeps_lowest_rank(self):
        # Two draft names resolving to one player_key: the best (lowest)
        # positional rank wins and the collision is counted. Reverting min->max
        # in the module turns this red.
        entries = {
            "a": {"pos": "RB", "rank_ecr": 30, "name": "A"},
            "b": {"pos": "RB", "rank_ecr": 12, "name": "B"},
        }
        ranks, report = self._load(entries, {"A": 42, "B": 42})
        self.assertEqual(ranks, {42: 12})
        self.assertEqual(report["collisions"], 1)
        self.assertEqual(report["resolved"], 2)

    def test_collision_order_does_not_matter(self):
        # Same collision with the better rank first: still the lowest wins.
        entries = {
            "a": {"pos": "WR", "rank_ecr": 3, "name": "A"},
            "b": {"pos": "WR", "rank_ecr": 40, "name": "B"},
        }
        ranks, report = self._load(entries, {"A": 7, "B": 7})
        self.assertEqual(ranks, {7: 3})
        self.assertEqual(report["collisions"], 1)

    def test_report_counts_on_mixed_draft(self):
        entries = {
            "k": {"pos": "K", "rank_ecr": 1, "name": "K"},          # skipped
            "rb1": {"pos": "RB", "rank_ecr": 0, "name": "Rb1"},      # bad rank
            "rb2": {"pos": "RB", "rank_ecr": 20, "name": "Rb2"},     # resolves
            "rb3": {"pos": "RB", "rank_ecr": 4, "name": "Rb3"},      # collision
            "wr1": {"pos": "WR", "rank_ecr": 8, "name": "Wr1"},      # unmatched
            "te1": {"pos": "TE", "rank_ecr": 2, "name": "Te1"},      # resolves
        }
        ranks, report = self._load(entries, {
            "Rb2": 10, "Rb3": 10, "Te1": 20,  # "Wr1" -> None
        })
        self.assertEqual(ranks, {10: 4, 20: 2})
        self.assertEqual(report, {
            "draft_entries": 6,
            "skill_entries": 5,   # all but the K
            "resolved": 3,        # Rb2, Rb3, Te1
            "unmatched": 1,       # Wr1
            "collisions": 1,      # Rb2/Rb3 -> key 10
            "bad_ranks": 1,       # Rb1
        })

    def test_default_draft_path_is_data_inputs(self):
        # The no-argument default points at the vendored draft source.
        self.assertTrue(preseason_ecr.DRAFT_ECR_JSON.endswith(
            os.path.join("data", "inputs", "ecr_draft.json")))


class TestAnnotateRows(PreseasonEcrTestCase):
    def test_sets_field_from_map(self):
        rows = [{"player_key": 1}, {"player_key": 2}]
        out = annotate_rows(rows, {1: 12})
        self.assertIs(out, rows)
        self.assertEqual(rows[0][FIELD], 12)
        self.assertIsNone(rows[1][FIELD])  # key absent from the map -> None

    def test_absent_player_key_is_none_never_zero(self):
        rows = [{"name": "no key"}, {"player_key": None}]
        annotate_rows(rows, {5: 9})
        for row in rows:
            self.assertIsNone(row[FIELD])

    def test_never_zero_when_map_lacks_key(self):
        rows = [{"player_key": 99}]
        annotate_rows(rows, {1: 1})
        self.assertIsNone(rows[0][FIELD])
        self.assertNotEqual(rows[0][FIELD], 0)

    def test_key_coerced_from_string(self):
        # int(key) is applied, so a string player_key still looks up.
        rows = [{"player_key": "7"}]
        annotate_rows(rows, {7: 3})
        self.assertEqual(rows[0][FIELD], 3)


class TestProvenanceNote(unittest.TestCase):
    def test_keys_pinned(self):
        note = provenance_note()
        self.assertEqual(set(note), {"source", "source_file", "semantics"})
        self.assertEqual(note["source"], "FantasyPros draft ECR (preseason)")
        self.assertEqual(note["source_file"], "data/inputs/ecr_draft.json")

    def test_semantics_states_positional_and_null_not_zero(self):
        note = provenance_note()
        self.assertIn("POSITIONAL", note["semantics"])
        self.assertIn("never zero", note["semantics"])


if __name__ == "__main__":
    unittest.main()
