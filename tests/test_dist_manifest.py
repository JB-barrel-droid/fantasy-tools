"""Tests for pipelines/dist_manifest.py (JEG-31 preview deploys).

The manifest is what lets a preview claim "same bytes as production". Each test
targets one way that claim could silently break:

- any byte change in any file must change the root hash;
- the one permitted exception (generated_at in reference-freshness.json) must be
  ignored, and ONLY that field of ONLY that file;
- manifests from different days must be refused as not comparable;
- an unreadable freshness file must fail closed.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))
import dist_manifest as dm  # noqa: E402

FRESH = "assets/reference-freshness.json"


def write_tree(root: Path, generated_at="2026-10-01T10:00:00+00:00", today="2026-10-01",
               extra=None):
    files = {
        "index.html": b"<html>tv-20261001-1633-abc1234</html>",
        "assets/curve-widget.js": b"console.log('widget');",
        "modules/players.json": b'{"a":1}',
    }
    files.update(extra or {})
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    fresh = {"generated_at": generated_at, "today": today,
             "summary": {"stale_count": 6}, "items": [{"key": "k", "age_days": 8}]}
    (root / FRESH).write_text(json.dumps(fresh))


class DistManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tree(self, name, **kw):
        root = self.tmp / name
        root.mkdir()
        write_tree(root, **kw)
        return root

    def test_identical_trees_have_identical_root(self):
        a = dm.build_manifest(self.tree("a"))
        b = dm.build_manifest(self.tree("b"))
        self.assertEqual(a["root_sha256"], b["root_sha256"])
        self.assertTrue(dm.compare_manifests(a, b)["equal"])

    def test_single_byte_change_changes_root(self):
        a = dm.build_manifest(self.tree("a"))
        root_b = self.tree("b")
        (root_b / "assets/curve-widget.js").write_bytes(b"console.log('widgeT');")
        b = dm.build_manifest(root_b)
        self.assertNotEqual(a["root_sha256"], b["root_sha256"])
        result = dm.compare_manifests(a, b)
        self.assertFalse(result["equal"])
        self.assertEqual(["differs: assets/curve-widget.js"], result["differences"])

    def test_generated_at_alone_is_ignored(self):
        a = dm.build_manifest(self.tree("a", generated_at="2026-10-01T10:00:00+00:00"))
        b = dm.build_manifest(self.tree("b", generated_at="2026-10-01T23:59:59+00:00"))
        self.assertEqual(a["root_sha256"], b["root_sha256"])
        self.assertTrue(dm.compare_manifests(a, b)["equal"])

    def test_other_freshness_fields_are_not_ignored(self):
        a = dm.build_manifest(self.tree("a"))
        root_b = self.tree("b")
        doc = json.loads((root_b / FRESH).read_text())
        doc["summary"]["stale_count"] = 7
        (root_b / FRESH).write_text(json.dumps(doc))
        b = dm.build_manifest(root_b)
        self.assertNotEqual(a["root_sha256"], b["root_sha256"])
        self.assertEqual([f"differs: {FRESH}"], dm.compare_manifests(a, b)["differences"])

    def test_generated_at_is_ignored_only_in_the_freshness_file(self):
        # A file with the same field name elsewhere must still be compared.
        a_root = self.tree("a", extra={"modules/other.json": b'{"generated_at":"x"}'})
        b_root = self.tree("b", extra={"modules/other.json": b'{"generated_at":"y"}'})
        a, b = dm.build_manifest(a_root), dm.build_manifest(b_root)
        self.assertNotEqual(a["root_sha256"], b["root_sha256"])
        self.assertEqual(["differs: modules/other.json"],
                         dm.compare_manifests(a, b)["differences"])

    def test_added_or_removed_file_changes_root(self):
        a = dm.build_manifest(self.tree("a"))
        b = dm.build_manifest(self.tree("b", extra={"modules/new.json": b"{}"}))
        self.assertNotEqual(a["root_sha256"], b["root_sha256"])
        self.assertEqual(["only in second: modules/new.json"],
                         dm.compare_manifests(a, b)["differences"])
        self.assertEqual(["only in first: modules/new.json"],
                         dm.compare_manifests(b, a)["differences"])

    def test_different_days_are_not_comparable(self):
        a = dm.build_manifest(self.tree("a", today="2026-10-01"))
        b = dm.build_manifest(self.tree("b", today="2026-10-02"))
        result = dm.compare_manifests(a, b)
        self.assertFalse(result["comparable"])
        self.assertFalse(result["equal"])
        self.assertIn("different days", result["reason"])

    def test_unparsable_freshness_file_fails_closed(self):
        root = self.tree("a")
        (root / FRESH).write_text("{not json")
        with self.assertRaises(SystemExit) as ctx:
            dm.build_manifest(root)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_empty_or_missing_dir_fails_closed(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        with self.assertRaises(SystemExit):
            dm.build_manifest(empty)
        with self.assertRaises(SystemExit):
            dm.build_manifest(self.tmp / "nope")

    def test_compare_rejects_foreign_schema(self):
        a = dm.build_manifest(self.tree("a"))
        with self.assertRaises(SystemExit):
            dm.compare_manifests(a, {"schema": "something-else"})


if __name__ == "__main__":
    unittest.main()
