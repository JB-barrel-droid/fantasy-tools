#!/usr/bin/env python3
"""JEG-205: the hourly vintage check triggers a rebuild on pipeline-code changes.

The code-version stamp is additive to the existing vintage logic and
fail-safe: any failure to compute the hash or read the state triggers a
rebuild rather than skipping one. All tests are hermetic (temp dirs, no
network, no git).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import check_source_vintage as csv_mod


def _make_tree(files):
    """Build a fake repo root with a pipelines/ dir holding {relpath: text}."""
    d = Path(tempfile.mkdtemp())
    (d / "pipelines").mkdir()
    for rel, content in files.items():
        p = d / "pipelines" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return d


class PipelinesCodeHashTests(unittest.TestCase):
    def test_hash_is_deterministic(self):
        files = {"a.py": "x = 1\n", "sub/b.py": "y = 2\n"}
        self.assertEqual(
            csv_mod.compute_pipelines_code_hash(_make_tree(files)),
            csv_mod.compute_pipelines_code_hash(_make_tree(files)),
        )

    def test_hash_is_sensitive_to_content(self):
        self.assertNotEqual(
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 1\n"})),
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 2\n"})),
        )

    def test_hash_is_sensitive_to_filenames(self):
        self.assertNotEqual(
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 1\n"})),
            csv_mod.compute_pipelines_code_hash(_make_tree({"b.py": "x = 1\n"})),
        )

    def test_hash_ignores_bytecode_churn(self):
        """__pycache__ and .pyc files never count as a code change."""
        d = _make_tree({"a.py": "x = 1\n"})
        cache = d / "pipelines" / "__pycache__"
        cache.mkdir()
        (cache / "a.pyc").write_bytes(b"\x00\x01\x02")
        (d / "pipelines" / "stray.pyc").write_bytes(b"\x00\x01\x02")
        self.assertEqual(
            csv_mod.compute_pipelines_code_hash(d),
            csv_mod.compute_pipelines_code_hash(_make_tree({"a.py": "x = 1\n"})),
        )

    def test_missing_pipelines_dir_raises(self):
        with self.assertRaises(FileNotFoundError):
            csv_mod.compute_pipelines_code_hash(Path(tempfile.mkdtemp()))


class CodeChangeTriggerTests(unittest.TestCase):
    def _state_with(self, root, payload):
        state = root / "state.json"
        state.write_text(json.dumps(payload), encoding="utf-8")
        return state

    def test_matching_hash_means_no_trigger(self):
        d = _make_tree({"a.py": "x = 1\n"})
        h = csv_mod.compute_pipelines_code_hash(d)
        r = csv_mod.check_code_change(
            state_path=self._state_with(d, {"last_code_hash": h}), repo_root=d
        )
        self.assertFalse(r["code_changed"])
        self.assertEqual(r["code_hash"], h)

    def test_differing_hash_triggers(self):
        """Simulated pipeline-code change with no vintage drift triggers."""
        d = _make_tree({"a.py": "x = 1\n"})
        r = csv_mod.check_code_change(
            state_path=self._state_with(d, {"last_code_hash": "deadbeef"}), repo_root=d
        )
        self.assertTrue(r["code_changed"])
        self.assertEqual(r["code_hash"], csv_mod.compute_pipelines_code_hash(d))

    def test_missing_state_file_triggers_fail_safe(self):
        d = _make_tree({"a.py": "x = 1\n"})
        r = csv_mod.check_code_change(state_path=d / "nope.json", repo_root=d)
        self.assertTrue(r["code_changed"])

    def test_corrupt_state_file_triggers_fail_safe(self):
        d = _make_tree({"a.py": "x = 1\n"})
        state = d / "state.json"
        state.write_text("not json{{{", encoding="utf-8")
        r = csv_mod.check_code_change(state_path=state, repo_root=d)
        self.assertTrue(r["code_changed"])

    def test_unhashable_tree_triggers_fail_safe(self):
        d = Path(tempfile.mkdtemp())  # no pipelines/ dir at all
        r = csv_mod.check_code_change(state_path=d / "s.json", repo_root=d)
        self.assertTrue(r["code_changed"])
        self.assertIsNone(r["code_hash"])

    def test_record_code_hash_round_trips(self):
        d = Path(tempfile.mkdtemp())
        state = d / "s.json"
        csv_mod.record_code_hash(state, "abc123")
        data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(data["last_code_hash"], "abc123")

    def test_record_preserves_other_state_fields(self):
        d = Path(tempfile.mkdtemp())
        state = self._state_with(d, {"other": 1})
        csv_mod.record_code_hash(state, "abc123")
        data = json.loads(state.read_text(encoding="utf-8"))
        self.assertEqual(data["last_code_hash"], "abc123")
        self.assertEqual(data["other"], 1)

    def test_recorded_hash_silences_next_check(self):
        """Record-then-check is the loop guard: exactly one dispatch per change."""
        d = _make_tree({"a.py": "x = 1\n"})
        state = d / "state.json"
        first = csv_mod.check_code_change(state_path=state, repo_root=d)
        self.assertTrue(first["code_changed"])
        csv_mod.record_code_hash(state, first["code_hash"])
        second = csv_mod.check_code_change(state_path=state, repo_root=d)
        self.assertFalse(second["code_changed"])


if __name__ == "__main__":
    unittest.main()
