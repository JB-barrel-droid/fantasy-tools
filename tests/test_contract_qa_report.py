"""JEG-491: the contract QA report fails on a failing line and lists pending gaps."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import contract_qa_report as qa  # noqa: E402

TEXT = "- **GL-01** The brand is Data Driven Football. More.\n- **GL-07** Customize *(to build: JEG-498)*. Lists.\n"


class ReportTest(unittest.TestCase):
    def test_summaries(self):
        s = qa.line_summaries(TEXT)
        self.assertEqual(s["GL-01"], "The brand is Data Driven Football")
        self.assertNotIn("to build", s["GL-07"])

    def test_passing_report(self):
        out = qa.render_report({"GL-01": []}, {"GL-07": "JEG-498"}, qa.line_summaries(TEXT), "t",
                               status={"JEG-498": "Todo"})
        self.assertIn("**Result: PASS**", out)
        self.assertIn("| GL-07 | JEG-498 | Todo |", out)

    def test_failing_line_fails_report(self):
        out = qa.render_report({"GL-01": ["Vegas in header"]}, {}, {}, "t")
        self.assertIn("**Result: FAIL**", out)
        self.assertIn("| GL-01 | FAIL | Vegas in header |", out)

    def test_page_errors_fail_report(self):
        self.assertIn("**Result: FAIL**", qa.render_report({"GL-01": []}, {}, {}, "t", page_errors=["x"]))


if __name__ == "__main__":
    unittest.main()
