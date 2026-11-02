"""Find a trade search and grouping are unchanged by display work (JEG-1019 review).

Seeded 9v9 rosters (tests/fixtures/finder_search_signature.js: LCG seed 7, four charts) searched at 3-for-3 and 2-for-2. The
golden file holds a sha256 of every trade and group (members, edge, score, order) produced by origin/main's finder.js before the
JEG-1019 change; this branch must reproduce it exactly. These are synthetic rosters, not the
"221-trade" 9v9 fixture of the JEG-972 log entry, which was not kept. Change the golden file only with a deliberate search change.

JEG-1403 (Jeremy: "I'd still want to see for even one trade chart and then we can use filters") re-pinned it: the search lists a
trade when one chart has the other side even, not 3 of 4, giving 3-for-3 929 trades / 55 groups and 2-for-2 155 / 29. Main at
951f95df had already moved off the JEG-1019 golden before that, through later search changes that did not re-pin it: 3-for-3
73 / 25 (sha256 f6c357e8...) and 2-for-2 15 / 9 (sha256 b878bcb4...).

Discrimination: test_guard_fails_on_broken_builds changes the group order, the best-trade pick and a trade's score and requires a mismatch.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
SCRIPT = ROOT / "tests" / "fixtures" / "finder_search_signature.js"
GOLDEN = json.loads((ROOT / "tests" / "fixtures" / "finder_search_golden.json").read_text(encoding="utf-8"))


def signature(finder: Path) -> dict:
    out = subprocess.run(["node", str(SCRIPT), str(finder)], capture_output=True, text=True, timeout=120, check=True)
    return json.loads(out.stdout)


class FinderSearchUnchangedTest(unittest.TestCase):
    def test_matches_origin_main(self):
        self.assertEqual(signature(FINDER_JS), GOLDEN)

    def test_guard_fails_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        mutants = {
            "group order": ("groups.sort((a, b) => b.bestEdge - a.bestEdge", "groups.sort((a, b) => a.bestEdge - b.bestEdge"),
            "best trade pick": ("b.score - a.score || b.edge - a.edge || idOf(a)", "a.score - b.score || b.edge - a.edge || idOf(a)"),
            "group key": ("const key = heavy.map(r => String(r.player_key)).join(\",\");", "const key = String(core.player_key);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(name):
                self.assertIn(old, source, f"stale anchor for {name!r}")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertNotEqual(signature(path), GOLDEN, f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
