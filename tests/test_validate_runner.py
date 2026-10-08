"""scripts/validate.py runs the same lines `make validate` does (2026-10-08).

Windows has no make, so local validate is run through scripts/validate.py.
If it resolved prerequisites differently from make, a local green would not
mean the deploy gate is green.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("validate_runner", ROOT / "scripts" / "validate.py")
validate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate)


class ValidateRunnerTest(unittest.TestCase):
    def test_prerequisites_run_in_order_once_before_the_recipe(self):
        rules = validate.parse_rules(
            "VAR ?= x\n"
            "all: a b  # comment\n\techo all\n"
            "a: b\n\t@echo a\n"
            "b:\n\t# skipped\n\t-echo b\n"
        )
        self.assertEqual(validate.commands_for("all", rules), ["echo b", "echo a", "echo all"])

    def test_real_validate_target_covers_every_gate_line(self):
        rules = validate.parse_rules((ROOT / "Makefile").read_text(encoding="utf-8"))
        commands = validate.commands_for("validate", rules)
        prerequisites, _ = rules["validate"]
        expected = [line for dep in prerequisites for line in rules[dep][1]]
        self.assertEqual(commands, expected)
        self.assertIn("python3 -m unittest tests.test_static_export", commands)

    def test_only_today_is_expanded(self):
        self.assertIn("--today 2026-10-08", validate.expand("python3 x.py --today $(TODAY)", "2026-10-08"))
        with self.assertRaises(SystemExit):
            validate.expand("python3 x.py $(OUT)", "2026-10-08")


if __name__ == "__main__":
    unittest.main()
