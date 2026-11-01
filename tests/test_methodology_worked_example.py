"""docs/methodology.md's worked example is generated, and stays current (JEG-1397).

Finding J1393-04: the "Worked example" and "Hand-check one value" text kept
the old D'Hondt bench, the first-non-starter starter line and the old fill
sets after the code moved, so its reference numbers (RB Delta "starter line
10, waiver line 7, DDF 48.511113") no longer reproduced. The section is now
written by tools/methodology_worked_example.py from the fixture through the
spec reference; this test regenerates it and fails when the doc differs.
Fix a failure by running the generator, never by editing the block.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "methodology_worked_example", REPO / "tools" / "methodology_worked_example.py")
gen = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gen
spec.loader.exec_module(gen)


class MethodologyWorkedExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = gen.DOC.read_text(encoding="utf-8")
        cls.fx = json.loads(gen.FIXTURE.read_text(encoding="utf-8"))
        cls.block = gen.render(cls.fx)

    def test_doc_block_matches_generator(self):
        have = gen.current_block(self.doc)
        self.assertIsNotNone(have, "docs/methodology.md has no generated worked-example markers")
        self.assertEqual(have, self.block,
                         "docs/methodology.md worked example is stale: run python3 tools/methodology_worked_example.py")

    def test_markers_appear_once(self):
        self.assertEqual(self.doc.count(gen.BEGIN), 1)
        self.assertEqual(self.doc.count(gen.END), 1)

    def test_block_carries_the_current_reference_numbers(self):
        # The J1393-04 numbers, read independently of the generator's text:
        # if the fixture or the spec reference moves, the doc must move too.
        res = gen.Ctx(self.fx).run()
        rb = res["sources"]["p1"]["positions"]["RB"]
        row = res["rows"][201]
        for x in (rb["starter_line"], rb["waiver_value"], row["ddf_blended"]["value"],
                  row["ddf_projections"]["value"], res["indexed"]["c5"]["factor"]):
            self.assertIn(gen.f(x), self.block)
        self.assertIn("Starter line 12 = the midpoint", self.block)
        self.assertIn("**DDF Value** is **52.165616**", self.block)
        self.assertIn("48.084613", self.block)
        self.assertIn("0.525453", self.block)
        for stale in ("48.511113", "0.519241", "0.785708", "3.054707", "starter line 10"):
            self.assertFalse(stale in self.doc, f"stale worked-example text {stale!r} is still in the doc")

    def test_both_modes_are_shown_and_labelled(self):
        self.assertIn("**Legacy slices mode**", self.block)
        self.assertIn("**Current rule: expected starts", self.block)
        self.assertIn("Hand-check one value (expected starts)", self.block)

    def test_stale_text_fails(self):
        # A hand edit inside the block is caught.
        broken = self.doc.replace("**52.165616**", "**48.511113**", 1)
        self.assertNotEqual(gen.current_block(broken), self.block)
        # A doc without markers is caught (main before JEG-1397).
        with self.assertRaises(SystemExit):
            gen.current_block(self.doc.replace(gen.BEGIN, ""))
        # A second, stale block is caught too, by the check and by splice.
        doubled = self.doc + "\n" + self.block.replace("**52.165616**", "**48.511113**") + "\n"
        with self.assertRaises(SystemExit):
            gen.current_block(doubled)
        with self.assertRaises(SystemExit):
            gen.splice(doubled, self.block)

    def test_vp25_states_the_midpoint_rule(self):
        vp25 = self.doc[self.doc.index("5. **Starter line `l_p`**"):self.doc.index("6. **Per player**")]
        self.assertIn("midpoint of the last starter", vp25)
        self.assertFalse("first non-starter) if it exists" in vp25, "VP-2.5 still states the old rule")


if __name__ == "__main__":
    unittest.main()
