"""JEG-1170: the test-core shards must together run exactly test-core.

preview.yml runs `make validate` as `make validate-base` in one job plus test-core-shard-N in
parallel matrix jobs (the single job took ~26 minutes). pages.yml still runs `make validate`.
A test-core line in two shards runs twice; a line in none is silently dropped from the PR gate.
Both fail here, as does validate drifting from validate-base + test-core, or the preview matrix
not listing exactly the shards the Makefile defines.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = ".github/workflows/preview.yml"


def recipe_lines(makefile_text, target):
    """A target's recipe commands, in order (comments and blank lines dropped, duplicates kept)."""
    lines = makefile_text.splitlines()
    start = next(i for i, line in enumerate(lines) if re.match(rf"{re.escape(target)}\s*:", line))
    out = []
    for line in lines[start + 1:]:
        if not line.startswith("\t"):
            break
        cmd = line.strip()
        if cmd and not cmd.startswith("#"):
            out.append(cmd)
    return out


def prerequisites(makefile_text, target):
    m = re.search(rf"^{re.escape(target)}:([^\n]*)$", makefile_text, re.M)
    return m.group(1).split() if m else None


def shard_targets(makefile_text):
    nums = sorted(int(n) for n in re.findall(r"^test-core-shard-(\d+):", makefile_text, re.M))
    return [f"test-core-shard-{n}" for n in nums]


def shard_problems(makefile_text):
    full = recipe_lines(makefile_text, "test-core")
    found, seen = [], {}
    for target in shard_targets(makefile_text):
        for cmd in recipe_lines(makefile_text, target):
            if cmd in seen:
                found.append(f"{cmd}: in {seen[cmd]} and {target}" if seen[cmd] != target else f"{cmd}: twice in {target}")
            seen.setdefault(cmd, target)
    for cmd in full:
        if cmd not in seen:
            found.append(f"{cmd}: in test-core but in no shard")
    for cmd in seen:
        if cmd not in full:
            found.append(f"{cmd}: in a shard but not in test-core")
    if len(full) != len(set(full)):
        found.append("test-core runs a line twice")
    return found


def validate_problems(makefile_text):
    validate, base = prerequisites(makefile_text, "validate"), prerequisites(makefile_text, "validate-base")
    if validate is None or base is None:
        return ["validate and validate-base must both exist"]
    if "test-core" not in validate:
        return ["validate must run test-core"]
    if [p for p in validate if p != "test-core"] != base:
        return [f"validate minus test-core {[p for p in validate if p != 'test-core']} != validate-base {base}"]
    if recipe_lines(makefile_text, "validate") or recipe_lines(makefile_text, "validate-base"):
        return ["validate and validate-base must have no recipe of their own"]
    return []


def matrix_problems(makefile_text, preview_text):
    m = re.search(r"^\s+shard:\s*\[([^\]]*)\]", preview_text, re.M)
    if not m:
        return ["preview.yml has no shard matrix"]
    listed = sorted(int(n) for n in re.findall(r"\d+", m.group(1)))
    defined = sorted(int(t.rsplit("-", 1)[1]) for t in shard_targets(makefile_text))
    if listed != defined:
        return [f"preview.yml matrix shards {listed} != Makefile shards {defined}"]
    if "make test-core-shard-${{ matrix.shard }}" not in preview_text:
        return ["preview.yml must run make test-core-shard-${{ matrix.shard }}"]
    return []


class ValidateShardsTest(unittest.TestCase):
    def setUp(self):
        self.makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
        self.preview = (ROOT / PREVIEW).read_text(encoding="utf-8")

    def test_shards_union_equals_test_core_without_overlap(self):
        self.assertEqual([], shard_problems(self.makefile))

    def test_validate_is_validate_base_plus_test_core(self):
        self.assertEqual([], validate_problems(self.makefile))

    def test_preview_matrix_lists_exactly_the_shards(self):
        self.assertEqual([], matrix_problems(self.makefile, self.preview))

    def test_there_are_several_non_empty_shards(self):
        shards = shard_targets(self.makefile)
        self.assertGreaterEqual(len(shards), 3)
        for t in shards:
            self.assertGreater(len(recipe_lines(self.makefile, t)), 5, t)

    def test_a_line_dropped_from_every_shard_is_caught(self):
        victim = recipe_lines(self.makefile, "test-core-shard-2")[0]
        head, sep, tail = self.makefile.partition("test-core-shard-2:\n")
        broken = head + sep + tail.replace(f"\t{victim}\n", "", 1)
        self.assertNotEqual(self.makefile, broken)
        self.assertEqual([f"{victim}: in test-core but in no shard"], shard_problems(broken))

    def test_a_line_in_two_shards_is_caught(self):
        victim = recipe_lines(self.makefile, "test-core-shard-1")[0]
        broken = self.makefile.replace("test-core-shard-2:\n", f"test-core-shard-2:\n\t{victim}\n", 1)
        self.assertEqual([f"{victim}: in test-core-shard-1 and test-core-shard-2"], shard_problems(broken))

    def test_a_line_only_in_a_shard_is_caught(self):
        extra = "python3 -m unittest tests.test_brand_new_core"
        broken = self.makefile.replace("test-core-shard-3:\n", f"test-core-shard-3:\n\t{extra}\n", 1)
        self.assertEqual([f"{extra}: in a shard but not in test-core"], shard_problems(broken))

    def test_a_line_added_to_test_core_only_is_caught(self):
        extra = "python3 -m unittest tests.test_brand_new_core"
        broken = self.makefile.replace("test-core:\n", f"test-core:\n\t{extra}\n", 1)
        self.assertEqual([f"{extra}: in test-core but in no shard"], shard_problems(broken))

    def test_a_dropped_shard_target_is_caught(self):
        last = shard_targets(self.makefile)[-1]
        broken = self.makefile.replace(f"{last}:\n", "not-a-shard:\n", 1)
        self.assertTrue(any("in no shard" in p for p in shard_problems(broken)))
        self.assertTrue(matrix_problems(broken, self.preview))

    def test_validate_drift_from_validate_base_is_caught(self):
        broken = self.makefile.replace(
            "validate: reference sync guard-harness test-core value-check-compare test-integration\n",
            "validate: reference sync guard-harness test-core value-check-compare test-integration lint\n", 1)
        self.assertNotEqual(self.makefile, broken)
        self.assertTrue(validate_problems(broken))
        broken = self.makefile.replace("validate-base: reference sync guard-harness",
                                       "validate-base: reference sync", 1)
        self.assertNotEqual(self.makefile, broken)
        self.assertTrue(validate_problems(broken))

    def test_validate_without_test_core_is_caught(self):
        broken = self.makefile.replace("guard-harness test-core value-check-compare", "guard-harness value-check-compare", 1)
        self.assertNotEqual(self.makefile, broken)
        self.assertEqual(["validate must run test-core"], validate_problems(broken))

    def test_matrix_missing_a_shard_is_caught(self):
        broken = re.sub(r"(shard:\s*\[[^\]]*?),\s*\d+\]", r"\1]", self.preview, count=1)
        self.assertNotEqual(self.preview, broken)
        self.assertTrue(matrix_problems(self.makefile, broken))

    def test_matrix_with_an_extra_shard_is_caught(self):
        broken = re.sub(r"(shard:\s*\[[^\]]*)\]", r"\1, 99]", self.preview, count=1)
        self.assertNotEqual(self.preview, broken)
        self.assertTrue(matrix_problems(self.makefile, broken))

    def test_matrix_not_running_the_shard_target_is_caught(self):
        broken = self.preview.replace("make test-core-shard-${{ matrix.shard }}", "make test-core")
        self.assertNotEqual(self.preview, broken)
        self.assertTrue(matrix_problems(self.makefile, broken))


if __name__ == "__main__":
    unittest.main()
