"""JEG-1117: the three render-sweep shards must together run exactly test-render-extra.

render-sweep.yml runs test-render-sweep-1/2/3 as a matrix (the single-job sweep hit the
60-minute timeout on 2026-10-26). A module in two shards runs twice; a module in none is
silently dropped from the daily sweep. Both fail here, and the workflow must run every shard.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARD_TARGETS = ["test-render-sweep-1", "test-render-sweep-2", "test-render-sweep-3"]


def recipe_modules(makefile_text, target):
    """Module names run by a target's recipe lines, in order (duplicates kept)."""
    lines = makefile_text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"{re.escape(target)}\s*:", line))
    out = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        found = re.fullmatch(r"\tpython3 -m unittest tests\.(\w+(?:\.\w+)*)", line.rstrip())
        if line.strip() and not line.strip().startswith("#"):
            assert found, f"{target}: unexpected recipe line {line!r}"
            out.append(found.group(1))
    return out


def problems(makefile_text, shard_targets=SHARD_TARGETS, full_target="test-render-extra"):
    full = recipe_modules(makefile_text, full_target)
    shards = {t: recipe_modules(makefile_text, t) for t in shard_targets}
    found = []
    seen = {}
    for target, modules in shards.items():
        for m in modules:
            if m in seen:
                found.append(f"{m}: in {seen[m]} and {target}" if seen[m] != target else f"{m}: twice in {target}")
            seen.setdefault(m, target)
    for m in full:
        if m not in seen:
            found.append(f"{m}: in {full_target} but in no shard")
    for m in seen:
        if m not in full:
            found.append(f"{m}: in a shard but not in {full_target}")
    return found


class RenderSweepShardsTest(unittest.TestCase):
    def setUp(self):
        self.makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    def test_shards_union_equals_the_full_list_without_overlap(self):
        self.assertEqual([], problems(self.makefile))

    def test_every_shard_has_modules(self):
        for t in SHARD_TARGETS:
            self.assertGreater(len(recipe_modules(self.makefile, t)), 5, t)

    def test_a_class_target_must_match_in_full_and_one_shard(self):
        line = "\tpython3 -m unittest tests.test_uso_site_journey_contract.UsoJourneyContinuityTest\n"
        wired = self.makefile.replace("test-render-sweep-3:\n", "test-render-sweep-3:\n" + line, 1)
        wired = wired.replace("test-render-extra:\n", "test-render-extra:\n" + line, 1)
        self.assertEqual([], problems(wired))
        dropped = wired.replace("test-render-sweep-3:\n" + line, "test-render-sweep-3:\n", 1)
        self.assertIn("test_uso_site_journey_contract.UsoJourneyContinuityTest: in test-render-extra but in no shard", problems(dropped))

    def test_a_module_dropped_from_every_shard_is_caught(self):
        victim = recipe_modules(self.makefile, "test-render-sweep-2")[0]
        line = f"\tpython3 -m unittest tests.{victim}\n"
        head, sep, tail = self.makefile.partition("test-render-sweep-2:\n")
        broken = head + sep + tail.replace(line, "", 1)
        self.assertNotEqual(self.makefile, broken)
        self.assertEqual([f"{victim}: in test-render-extra but in no shard"], problems(broken))

    def test_a_module_in_two_shards_is_caught(self):
        victim = recipe_modules(self.makefile, "test-render-sweep-1")[0]
        broken = self.makefile.replace("test-render-sweep-2:\n", f"test-render-sweep-2:\n\tpython3 -m unittest tests.{victim}\n", 1)
        self.assertEqual([f"{victim}: in test-render-sweep-1 and test-render-sweep-2"], problems(broken))

    def test_a_module_only_in_a_shard_is_caught(self):
        broken = self.makefile.replace("test-render-sweep-3:\n", "test-render-sweep-3:\n\tpython3 -m unittest tests.test_v2_brand_new_render\n", 1)
        self.assertEqual(["test_v2_brand_new_render: in a shard but not in test-render-extra"], problems(broken))

    def test_workflow_runs_every_shard_and_only_on_dispatch(self):
        wf = (ROOT / ".github/workflows/render-sweep.yml").read_text(encoding="utf-8")
        for n in ("1", "2", "3"):
            self.assertIn(n, re.search(r"shard:\s*\[([^\]]*)\]", wf).group(1))
        self.assertIn("make test-render-sweep-${{ matrix.shard }}", wf)
        self.assertIn("fail-fast: false", wf)
        self.assertIn("timeout-minutes: 60", wf)
        self.assertIsNone(re.search(r"^\s*schedule:", wf, re.M))


if __name__ == "__main__":
    unittest.main()
