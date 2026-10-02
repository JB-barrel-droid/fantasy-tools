"""Regression test: canonical naming table never holds case-variant duplicates.

JEG-112: the canonical naming table (identity map) must never hold two
entries that differ only by case -- e.g. "Puka Nacua" vs "puka nacua".
Case-variant duplicates break identity resolution and can trip the
fail-closed ambiguity guard on what is really the same player.

This test covers:

  1. The committed identity snapshot has zero case-variant duplicates
     (the standing invariant). A negative test simulates a broken state
     and verifies the guard catches it.

  2. The write-path guard (``add_canonical_entry``, ``add_alias``) rejects
     inserts that would create a case-variant duplicate. A simulated
     broken insert proves the guard fires with a clear error.

  3. ``assert_no_case_duplicates`` and ``audit_file`` raise the same
     exception type with enough context for a regression report.

This test does NOT depend on Supabase or external services -- it loads the
vendored snapshot directly. Safe for CI / Pages deploys.
"""

import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

from identity_map_guard import (  # noqa: E402
    IDENTITY_SNAPSHOT,
    IdentityMapCaseVariantCollision,
    add_alias,
    add_canonical_entry,
    assert_no_case_duplicates,
    audit_file,
    load_snapshot,
    norm_case_only,
)


SNAPSHOT_PATH = Path(IDENTITY_SNAPSHOT)


class TestIdentitySnapshotClean(unittest.TestCase):
    """The committed snapshot is held to the zero-duplicates invariant."""

    def test_real_snapshot_loads(self):
        """The vendored file exists and parses as JSON with both sections."""
        self.assertTrue(SNAPSHOT_PATH.exists(),
                        f"identity snapshot missing at {SNAPSHOT_PATH}")
        snap = load_snapshot()
        self.assertIn("canonical", snap)
        self.assertIn("alias_to_canonical", snap)
        self.assertGreater(len(snap["canonical"]), 0,
                           "canonical section must not be empty")

    def test_real_snapshot_has_no_case_duplicates(self):
        """The committed file must satisfy the case-variant invariant."""
        try:
            assert_no_case_duplicates(load_snapshot())
        except IdentityMapCaseVariantCollision as e:
            self.fail(
                f"committed identity snapshot has a case-variant "
                f"duplicate: norm={e.norm!r}, raw={e.raw!r} -- see "
                f"docs/claude-log.md JEG-112 entry for the audit and "
                f"dedup steps"
            )

    def test_real_snapshot_audit_file_passes(self):
        """audit_file() is the commit-time guard; it must pass on the file."""
        try:
            audit_file()
        except IdentityMapCaseVariantCollision as e:
            self.fail(f"audit_file() failed on the committed snapshot: {e}")


class TestAssertNoCaseDuplicatesCatchesBreaks(unittest.TestCase):
    """The guard must detect simulated broken states (negative tests)."""

    def test_catches_canonical_duplicate(self):
        """Two canonical entries differing only by case -> guard fires."""
        snap = {
            "meta": {},
            "canonical": {
                "puka nacua": {"name": "Puka Nacua", "pos": "WR", "team": "LAR"},
                "Puka Nacua": {"name": "Puka Nacua", "pos": "WR", "team": "LAR"},
            },
            "alias_to_canonical": {},
        }
        with self.assertRaises(IdentityMapCaseVariantCollision) as cm:
            assert_no_case_duplicates(snap)
        self.assertEqual(cm.exception.norm, "puka nacua")
        # Two raw forms collapsed to one norm.
        self.assertIn("puka nacua", cm.exception.norm)

    def test_catches_alias_duplicate(self):
        """Two alias entries whose normalized form collides -> guard fires."""
        snap = {
            "meta": {},
            "canonical": {
                "puka nacua": {"name": "Puka Nacua", "pos": "WR", "team": "LAR"},
            },
            "alias_to_canonical": {
                "Puka Nacua": "puka nacua",
                "PUKA NACUA": "puka nacua",
            },
        }
        with self.assertRaises(IdentityMapCaseVariantCollision) as cm:
            assert_no_case_duplicates(snap)
        # "puka" is not in the nickname table, so the norm stays as-is.
        self.assertEqual(cm.exception.norm, "puka nacua")

    def test_catches_canonical_alias_cross_collision(self):
        """A new alias whose norm matches an existing canonical key is a
        case-variant duplicate from the other side; the guard fires."""
        snap = {
            "meta": {},
            "canonical": {
                "puka nacua": {"name": "Puka Nacua", "pos": "WR", "team": "LAR"},
            },
            "alias_to_canonical": {
                "PUKA NACUA": "puka nacua",
            },
        }
        with self.assertRaises(IdentityMapCaseVariantCollision) as cm:
            assert_no_case_duplicates(snap)
        self.assertEqual(cm.exception.norm, "puka nacua")

    def test_clean_snapshot_passes(self):
        """A well-formed snapshot passes cleanly."""
        snap = {
            "meta": {},
            "canonical": {
                "puka nacua": {"name": "Puka Nacua", "pos": "WR", "team": "LAR"},
                "josh allen": {"name": "Josh Allen", "pos": "QB", "team": "BUF"},
            },
            "alias_to_canonical": {
                "hollywood brown": "marquise brown",  # nickname, NOT a case dup
            },
        }
        assert_no_case_duplicates(snap)  # no raise


class TestWritePathGuardCatchesBreaks(unittest.TestCase):
    """add_canonical_entry / add_alias reject case-variant inserts."""

    def _seed(self) -> dict:
        return {
            "meta": {},
            "canonical": {
                "puka nacua": {"name": "Puka Nacua", "pos": "WR", "team": "LAR"},
            },
            "alias_to_canonical": {},
        }

    def test_add_canonical_rejects_exact_case_variant(self):
        """Inserting "Puka Nacua" when "puka nacua" exists -> guard fires."""
        snap = self._seed()
        with self.assertRaises(IdentityMapCaseVariantCollision) as cm:
            add_canonical_entry(
                snap, key="Puka Nacua", name="Puka Nacua",
                pos="WR", team="LAR",
            )
        self.assertEqual(cm.exception.norm, "puka nacua")
        self.assertEqual(cm.exception.existing_key, "puka nacua")

    def test_add_canonical_rejects_uppercase_variant(self):
        """All-caps variant is the same norm; still a duplicate."""
        snap = self._seed()
        with self.assertRaises(IdentityMapCaseVariantCollision):
            add_canonical_entry(
                snap, key="PUKA NACUA", name="Puka Nacua",
                pos="WR", team="LAR",
            )

    def test_add_canonical_rejects_mixed_case_variant(self):
        """Mixed-case variant is the same norm; still a duplicate."""
        snap = self._seed()
        with self.assertRaises(IdentityMapCaseVariantCollision):
            add_canonical_entry(
                snap, key="Puka NaCuA", name="Puka Nacua",
                pos="WR", team="LAR",
            )

    def test_add_canonical_accepts_new_player(self):
        """A genuinely new name inserts cleanly."""
        snap = self._seed()
        add_canonical_entry(
            snap, key="brock purdy", name="Brock Purdy",
            pos="QB", team="SF",
        )
        self.assertIn("brock purdy", snap["canonical"])
        self.assertEqual(snap["canonical"]["brock purdy"]["name"], "Brock Purdy")

    def test_add_alias_rejects_case_variant(self):
        """Inserting "Puka Nacua" -> "puka nacua" when canonical exists -> guard fires."""
        snap = self._seed()
        with self.assertRaises(IdentityMapCaseVariantCollision):
            add_alias(snap, alias="PUKA NACUA", target="puka nacua")

    def test_add_alias_rejects_duplicate_alias(self):
        """Same alias key with a DIFFERENT target -> guard fires (conflict)."""
        snap = {
            "meta": {},
            "canonical": {"josh allen": {"name": "Josh Allen", "pos": "QB",
                                          "team": "BUF"}},
            "alias_to_canonical": {"j allen": "josh allen"},
        }
        with self.assertRaises(IdentityMapCaseVariantCollision):
            add_alias(snap, alias="j allen", target="different player")

    def test_add_alias_idempotent_reinsert(self):
        """Re-inserting the exact same alias->target is a no-op, not an error."""
        snap = {
            "meta": {},
            "canonical": {"josh allen": {"name": "Josh Allen", "pos": "QB",
                                          "team": "BUF"}},
            "alias_to_canonical": {"j allen": "josh allen"},
        }
        add_alias(snap, alias="j allen", target="josh allen")
        self.assertEqual(snap["alias_to_canonical"]["j allen"], "josh allen")

    def test_add_alias_accepts_new_alias(self):
        """A new alias that doesn't collide inserts cleanly."""
        snap = self._seed()
        add_alias(snap, alias="p nacua", target="puka nacua")
        self.assertEqual(snap["alias_to_canonical"]["p nacua"], "puka nacua")


class TestSimulationOfCommittedSnapshot(unittest.TestCase):
    """End-to-end: a corrupted copy of the real snapshot is rejected by the
    guard. This is the negative-test the JEG-112 brief asked for ("every
    regression guard must prove it catches the bug it names")."""

    def test_simulated_corrupted_snapshot_fails_guard(self):
        snap = load_snapshot()
        # Make a copy and inject a case-variant duplicate into canonical.
        corrupted = copy.deepcopy(snap)
        # Pick a real key (Puka Nacua is in the snapshot) and add an upper
        # variant. We use the *value* of an existing key's display form to
        # make the injected row look like it "should" be a real player.
        if "puka nacua" not in corrupted["canonical"]:
            self.skipTest("real snapshot no longer contains 'puka nacua'")
        corrupted["canonical"]["PUKA NACUA"] = dict(
            corrupted["canonical"]["puka nacua"]
        )
        with self.assertRaises(IdentityMapCaseVariantCollision) as cm:
            assert_no_case_duplicates(corrupted)
        self.assertEqual(cm.exception.norm, "puka nacua")

    def test_simulated_corrupted_snapshot_fails_audit_file(self):
        """audit_file() must catch the same broken state when reading from disk."""
        snap = load_snapshot()
        corrupted = copy.deepcopy(snap)
        if "puka nacua" not in corrupted["canonical"]:
            self.skipTest("real snapshot no longer contains 'puka nacua'")
        corrupted["canonical"]["PUKA NACUA"] = dict(
            corrupted["canonical"]["puka nacua"]
        )
        # Write the corrupted snapshot to a temp file and audit it.
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as fh:
            json.dump(corrupted, fh)
            tmp_path = fh.name
        try:
            with self.assertRaises(IdentityMapCaseVariantCollision):
                audit_file(tmp_path)
        finally:
            os.unlink(tmp_path)


class TestNormalizationUsed(unittest.TestCase):
    """The write-path uses the canonical normalization, not a private rule."""

    def test_norm_case_only_is_strictly_narrower(self):
        """The case-only rule must not include nickname expansion."""
        from identity_map_guard import norm_case_only
        # "josh" is a nickname for "joshua" -- norm_case_only must NOT
        # rewrite it; the brief scopes the invariant to case-only.
        self.assertEqual(norm_case_only("Josh Allen"), "josh allen")
        self.assertEqual(norm_case_only("JOSH ALLEN"), "josh allen")
        # Punctuation and suffixes are NOT stripped: "Puka Nacua Jr." vs
        # "puka nacua" differ by more than case.
        self.assertEqual(norm_case_only("Puka Nacua Jr."), "puka nacua jr.")
        self.assertEqual(norm_case_only("Ja'Marr Chase"), "ja'marr chase")


if __name__ == "__main__":
    unittest.main()