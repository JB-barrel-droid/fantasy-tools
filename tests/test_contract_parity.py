"""Tests for pipelines.verify_contract_parity.

Covers:
  - compare_surface: identical inputs, one-field diff, missing keys both ways.
  - Float tolerance: 0.1 + 1e-10 vs 0.1 must compare as matched.
  - check_surface: fixture files → correct summary shape + parity_ok flag.

These tests do not hit Supabase or read any real dumps. Everything is
in-memory or on-disk fixtures.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest


# Make pipelines importable when running this file directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from pipelines.verify_contract_parity import (  # noqa: E402
    check_surface,
    compare_surface,
    load_json,
    main,
)


class TestCompareSurface(unittest.TestCase):
    def test_identical_inputs_match(self):
        result = compare_surface(
            [{"player": "a", "value": 1.0}],
            [{"player": "a", "value": 1.0}],
            ["player"],
            ["value"],
        )
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["mismatched"], [])
        self.assertEqual(result["missing_in_contract"], [])
        self.assertEqual(result["missing_in_static"], [])

    def test_one_field_diff_records_exact_key_field_values(self):
        contract = [{"player": "a", "value": 1.0}]
        static = [{"player": "a", "value": 2.0}]
        result = compare_surface(contract, static, ["player"], ["value"])
        self.assertEqual(result["matched"], 0)
        self.assertEqual(result["missing_in_contract"], [])
        self.assertEqual(result["missing_in_static"], [])
        self.assertEqual(len(result["mismatched"]), 1)
        mismatch = result["mismatched"][0]
        self.assertEqual(mismatch["key"], ("a",))
        self.assertEqual(mismatch["field"], "value")
        self.assertEqual(mismatch["contract"], 1.0)
        self.assertEqual(mismatch["static"], 2.0)

    def test_missing_in_contract_and_static(self):
        contract = [{"player": "a", "value": 1.0}]
        static = [{"player": "a", "value": 1.0}, {"player": "b", "value": 2.0}]
        result = compare_surface(contract, static, ["player"], ["value"])
        self.assertEqual(result["missing_in_contract"], [("b",)])
        self.assertEqual(result["missing_in_static"], [])

        contract = [{"player": "a", "value": 1.0}, {"player": "b", "value": 2.0}]
        static = [{"player": "a", "value": 1.0}]
        result = compare_surface(contract, static, ["player"], ["value"])
        self.assertEqual(result["missing_in_contract"], [])
        self.assertEqual(result["missing_in_static"], [("b",)])

    def test_float_tolerance(self):
        # 0.1 + 1e-10 vs 0.1 — well within 1e-9 tolerance.
        result = compare_surface(
            [{"id": "a", "v": 0.1 + 1e-10}],
            [{"id": "a", "v": 0.1}],
            ["id"],
            ["v"],
        )
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["mismatched"], [])

    def test_float_outside_tolerance_mismatches(self):
        result = compare_surface(
            [{"id": "a", "v": 0.1 + 1e-6}],
            [{"id": "a", "v": 0.1}],
            ["id"],
            ["v"],
        )
        self.assertEqual(result["matched"], 0)
        self.assertEqual(len(result["mismatched"]), 1)


class TestCheckSurface(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        for fn in os.listdir(self.tmp):
            os.unlink(os.path.join(self.tmp, fn))
        os.rmdir(self.tmp)

    def _write(self, name: str, payload) -> str:
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        return path

    def test_check_surface_summary_shape_parity_ok(self):
        c = self._write("c.json", [{"k": "x", "v": 1}])
        s = self._write("s.json", [{"k": "x", "v": 1}])
        result = check_surface("demo", c, s, ["k"], ["v"])
        self.assertEqual(result["surface"], "demo")
        self.assertEqual(result["matched"], 1)
        self.assertEqual(result["mismatched"], [])
        self.assertEqual(result["missing_in_contract"], [])
        self.assertEqual(result["missing_in_static"], [])
        self.assertTrue(result["parity_ok"])

    def test_check_surface_parity_not_ok_on_mismatch(self):
        c = self._write("c.json", [{"k": "x", "v": 1}])
        s = self._write("s.json", [{"k": "x", "v": 2}])
        result = check_surface("demo", c, s, ["k"], ["v"])
        self.assertFalse(result["parity_ok"])
        self.assertEqual(len(result["mismatched"]), 1)

    def test_check_surface_parity_not_ok_on_missing(self):
        c = self._write("c.json", [{"k": "x", "v": 1}])
        s = self._write("s.json", [{"k": "y", "v": 2}])
        result = check_surface("demo", c, s, ["k"], ["v"])
        self.assertFalse(result["parity_ok"])
        self.assertEqual(result["missing_in_static"], [("x",)])
        self.assertEqual(result["missing_in_contract"], [("y",)])

    def test_check_surface_handles_singleton_dict(self):
        # Singletons are normalized to one-row surfaces.
        c = self._write("c.json", {"product_key": "default", "v": 7})
        s = self._write("s.json", {"product_key": "default", "v": 7})
        result = check_surface("singleton", c, s, ["product_key"], ["v"])
        self.assertTrue(result["parity_ok"])


class TestLoadJson(unittest.TestCase):
    def test_loads(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"hello": "world"}, f)
            path = f.name
        try:
            data = load_json(path)
            self.assertEqual(data, {"hello": "world"})
        finally:
            os.unlink(path)


class TestMainEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        for root, _, files in os.walk(self.tmp):
            for fn in files:
                os.unlink(os.path.join(root, fn))
        for root, _, _ in os.walk(self.tmp):
            pass
        os.rmdir(self.tmp)

    def test_main_writes_report_and_returns_zero_when_parity(self):
        c_path = os.path.join(self.tmp, "c.json")
        s_path = os.path.join(self.tmp, "s.json")
        with open(c_path, "w") as f:
            json.dump([{"k": "x", "v": 1}], f)
        with open(s_path, "w") as f:
            json.dump([{"k": "x", "v": 1}], f)
        manifest_path = os.path.join(self.tmp, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(
                {
                    "surfaces": [
                        {
                            "name": "demo",
                            "contract": c_path,
                            "static": s_path,
                            "key_fields": ["k"],
                            "compare_fields": ["v"],
                        }
                    ]
                },
                f,
            )
        rc = main(manifest_path)
        self.assertEqual(rc, 0)
        report_path = os.path.join(self.tmp, "contract_parity_report.json")
        self.assertTrue(os.path.exists(report_path))
        with open(report_path) as f:
            report = json.load(f)
        self.assertEqual(len(report["results"]), 1)
        self.assertTrue(report["results"][0]["parity_ok"])

    def test_main_returns_nonzero_on_parity_failure(self):
        c_path = os.path.join(self.tmp, "c.json")
        s_path = os.path.join(self.tmp, "s.json")
        with open(c_path, "w") as f:
            json.dump([{"k": "x", "v": 1}], f)
        with open(s_path, "w") as f:
            json.dump([{"k": "x", "v": 9}], f)
        manifest_path = os.path.join(self.tmp, "manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(
                {
                    "surfaces": [
                        {
                            "name": "demo",
                            "contract": c_path,
                            "static": s_path,
                            "key_fields": ["k"],
                            "compare_fields": ["v"],
                        }
                    ]
                },
                f,
            )
        rc = main(manifest_path)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()