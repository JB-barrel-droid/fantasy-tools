"""JEG-976: no render module may be left out of every run list.

Every tests/test_*render*.py must be named in the Makefile (test-core,
test-unit-modules or test-render-extra) or be listed below as known red with its
ticket. Without this, a new render test that nobody wires runs nowhere, which is
how 77 test files went unrun. A known-red entry that is already wired is also an
error, so a fixed file is not left on the exemption list.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Red when run alone on main (2026-10-23). Remove an entry when its ticket is fixed and wire the file.
KNOWN_RED = {
    "test_v2_source_links_render": "JEG-983",
    "test_v2_writing_subtabs_order_render": "JEG-983",
}


def render_modules(tests_dir):
    return sorted(p.stem for p in tests_dir.glob("test_*render*.py"))


def problems(modules, makefile_text, known_red):
    out = []
    for m in modules:
        wired = re.search(rf"tests\.{re.escape(m)}\b", makefile_text) is not None
        if m in known_red and wired:
            out.append(f"{m}: listed as known red ({known_red[m]}) but already wired; drop the exemption")
        if m not in known_red and not wired:
            out.append(f"{m}: in no Makefile run list and not known red")
    for m in known_red:
        if m not in modules:
            out.append(f"{m}: known-red entry has no test file")
    return out


class RenderSweepCoverageTest(unittest.TestCase):
    def setUp(self):
        self.modules = render_modules(ROOT / "tests")
        self.makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    def test_every_render_module_is_wired_or_known_red(self):
        self.assertEqual([], problems(self.modules, self.makefile, KNOWN_RED))

    def test_an_unwired_green_module_is_caught(self):
        broken = self.makefile.replace("\tpython3 -m unittest tests.test_v2_names_render\n", "")
        self.assertNotEqual(self.makefile, broken)
        found = problems(self.modules, broken, KNOWN_RED)
        self.assertEqual(1, len(found))
        self.assertIn("test_v2_names_render", found[0])

    def test_class_target_counts_as_wiring_for_its_module(self):
        module = "test_uso_site_journey_contract"
        recipe = "\tpython3 -m unittest tests.test_uso_site_journey_contract.UsoJourneyContinuityTest\n"
        self.assertEqual([], problems([module], recipe, {}))

    def test_a_new_unlisted_module_is_caught(self):
        found = problems(self.modules + ["test_v2_brand_new_render"], self.makefile, KNOWN_RED)
        self.assertEqual(["test_v2_brand_new_render: in no Makefile run list and not known red"], found)

    def test_a_fixed_file_left_on_the_red_list_is_caught(self):
        red = dict(KNOWN_RED, test_v2_names_render="JEG-983")
        self.assertEqual(1, len(problems(self.modules, self.makefile, red)))


if __name__ == "__main__":
    unittest.main()
