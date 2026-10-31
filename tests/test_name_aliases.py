"""JEG-1388 (part of JEG-1202): the roster paste and the chat read one alias list.

pipelines/build_name_aliases.py writes the same [spelling, player_key] rows
into app/v2/roster-paste.js and supabase/functions/mcp/names.ts. Offline.

    python3 -m unittest tests.test_name_aliases
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_name_aliases as bna  # noqa: E402


def _block(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    body = text[text.index(bna.BEGIN):text.index(bna.END)]
    return [(a, int(k)) for a, k in re.findall(r'\[("(?:[^"\\]|\\.)*"), (\d+)\]', body)
            for a in [json.loads(a)]]


def _node(script):
    out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", "--input-type=module",
                          "-e", script], capture_output=True, text=True, timeout=60, cwd=str(ROOT))
    if out.returncode:
        raise AssertionError(out.stdout + out.stderr)
    return json.loads(out.stdout.strip().splitlines()[-1])


class OneList(unittest.TestCase):
    def test_generated_blocks_match_a_rebuild(self):
        self.assertEqual(bna.main(["--check"]), 0, "run python3 pipelines/build_name_aliases.py")

    def test_paste_and_chat_hold_the_same_rows(self):
        paste = _block("app/v2/roster-paste.js")
        self.assertEqual(paste, _block("supabase/functions/mcp/names.ts"))
        self.assertIn(("Zonovan Knight", 868), paste)
        self.assertIn(("Kenny Gainwell", 785), paste)

    def test_no_alias_is_another_players_name_or_two_players(self):
        rows, _ = bna.build()
        snapshot = json.loads((ROOT / bna.SNAPSHOT).read_text(encoding="utf-8"))
        names = {}
        for r in snapshot:
            for f in bna._forms(r["full_name"]):
                names.setdefault(f, set()).add(int(r["player_key"]))
        forms = {}
        for alias, key in rows:
            for f in bna._forms(alias):
                self.assertFalse(names.get(f, set()) - {key}, (alias, key))
            forms.setdefault(bna.plain(alias), set()).add(key)
        self.assertTrue(all(len(k) == 1 for k in forms.values()), forms)

    def test_a_spelling_that_is_a_duplicate_row_is_left_out(self):
        # Until JEG-1351 deletes 4660, "Mitch Tinsley" is also that row's own name.
        rows, dropped = bna.build()
        self.assertNotIn("Mitch Tinsley", [a for a, _ in rows])
        self.assertIn("Mitch Tinsley", [a for a, _, _ in dropped])


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class Matchers(unittest.TestCase):
    """Canonical names still win; an alias only reaches the player it belongs to."""

    def test_chat(self):
        r = _node("""
import { matchName } from "./supabase/functions/mcp/names.ts";
const knight = { player_key: 868, name: "Bam Knight", value: 1 };
const other = { player_key: 1, name: "Zonovan Knight", value: 2 };
const pick = (pool, q) => { const m = matchName(pool, q); return [m.match, m.player && m.player.player_key, m.note]; };
console.log(JSON.stringify({
  alias: pick([knight], "Zonovan Knight"),
  canonicalWins: pick([knight, other], "Zonovan Knight"),
  notInPool: pick([{ player_key: 5, name: "Bam Smith" }], "Zonovan Knight"),
  noKey: pick([{ name: "Bam Knight" }], "Zonovan Knight"),
}));
""")
        self.assertEqual(r["alias"], ["exact", 868, '"Zonovan Knight" is listed as Bam Knight'])
        self.assertEqual(r["canonicalWins"][:2], ["exact", 1])
        self.assertEqual(r["notInPool"][:2], ["none", None])
        self.assertEqual(r["noKey"][:2], ["none", None])

    def test_paste(self):
        r = _node("""
import { createRequire } from "node:module";
const P = createRequire(import.meta.url)("./app/v2/roster-paste.js");
const pick = (rows, name) => { const c = P.matchCandidate({ name, posHint: "RB" }, P.buildIndex(rows), {});
  return c.match ? c.match.player_key : null; };
const knight = { player_key: 868, name: "Bam Knight", pos: "RB", team: "ARI" };
console.log(JSON.stringify({
  alias: pick([knight], "Zonovan Knight"),
  canonicalWins: pick([knight, { player_key: 1, name: "Zonovan Knight", pos: "RB", team: "NYJ" }], "Zonovan Knight"),
  notInPool: pick([{ player_key: 5, name: "Bam Smith", pos: "RB" }], "Zonovan Knight"),
}));
""")
        self.assertEqual(r, {"alias": 868, "canonicalWins": 1, "notInPool": None})


if __name__ == "__main__":
    unittest.main()
