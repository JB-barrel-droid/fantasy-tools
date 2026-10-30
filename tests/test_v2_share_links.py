"""JEG-894: the Find a trade search link codec in app/v2/finder.js (encodeFinderHash / decodeFinderHash).

The link is a URL fragment: #find-trade?mine=<ids>&theirs=<ids>&size=<2|3|4>&km=<0|1>&kt=<0|1>&<league settings>.
Pure functions, driven through node:

  * a 2 x 16-man roster plus the league tail stays well under 2000 characters (the ticket's budget);
  * encode -> decode round-trips the ids, the package size and the two lineup ticks;
  * a crafted link cannot freeze the page: each side is capped at 40 ids and the extras are counted;
  * an id on both sides stays on "mine" and is dropped from "theirs";
  * an id the engine no longer prices is skipped and counted (knownKeys);
  * size is only 2/3/4 (anything else falls back to 2) and km/kt default on.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against mutated copies of finder.js
(the cap dropped, the cross-side rule dropped, `theirs` never encoded) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"

HARNESS = """
const F = require(process.argv[1]);
const mine = Array.from({length: 16}, (_, i) => ({key: String(1000 + i)}));
const theirs = Array.from({length: 16}, (_, i) => ({key: String(2000 + i)}));
const league = "scoring=ppr&teams=12&roster=QB1.RB2.WR2.TE1.FLEX2.SF0.BN6";
const hash = F.encodeFinderHash({mine, theirs, maxSize: 3, keepMine: false, keepTheirs: true}, league);
const round = F.decodeFinderHash(hash, null);
const big = F.encodeFinderHash({mine: Array.from({length: 60}, (_, i) => ({key: String(i)})), theirs: [{key: "999"}], maxSize: 2, keepMine: true, keepTheirs: true}, "");
const capped = F.decodeFinderHash(big, null);
const both = F.decodeFinderHash("#find-trade?mine=5,6&theirs=6,7", null);
const known = F.decodeFinderHash("#find-trade?mine=5,999&theirs=7", new Set(["5", "7"]));
const sizes = ["5", "x", "", "4"].map(v => F.decodeFinderHash(`#find-trade?mine=5&size=${v}`, null).size);
const flags = F.decodeFinderHash("#find-trade?mine=5", null);
const jumbled = F.decodeFinderHash("#find-trade?theirs=2&mine=1", null);
console.log(JSON.stringify({
  hash, len: hash.length, league,
  round: {mine: round.mine, theirs: round.theirs, size: round.size, km: round.keepMine, kt: round.keepTheirs, dropped: round.dropped, unknown: round.unknown},
  capped: {mine: capped.mine.length, theirs: capped.theirs.length, dropped: capped.dropped},
  both: {mine: both.mine, theirs: both.theirs, both: both.both},
  known: {mine: known.mine, theirs: known.theirs, unknown: known.unknown},
  sizes, flags: {km: flags.keepMine, kt: flags.keepTheirs},
  jumbled: {mine: jumbled.mine, theirs: jumbled.theirs},
}));
"""


def run(finder_js) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, str(finder_js)], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def check(finder_js: Path) -> list[str]:
    errors = []
    r = run(finder_js)

    # The budget: 2 x 16-man rosters plus the league tail.
    if r["len"] >= 2000:
        errors.append(f"a 2x16 link is {r['len']} chars, the budget is under 2000")
    if not r["hash"].startswith("#find-trade?"):
        errors.append(f"the link is not a #find-trade fragment: {r['hash'][:60]!r}")
    for part in ("mine=1000,", "theirs=2000,", "size=3", "km=0", "kt=1"):
        if part not in r["hash"]:
            errors.append(f"{part!r} missing from the link: {r['hash']!r}")
    if r["league"] not in r["hash"]:
        errors.append("the league settings are not carried in the link")

    # Round trip.
    want_mine = [str(1000 + i) for i in range(16)]
    want_theirs = [str(2000 + i) for i in range(16)]
    if r["round"]["mine"] != want_mine or r["round"]["theirs"] != want_theirs:
        errors.append(f"round trip lost ids: {r['round']}")
    if (r["round"]["size"], r["round"]["km"], r["round"]["kt"]) != (3, False, True):
        errors.append(f"round trip lost size / ticks: {r['round']}")
    if r["round"]["dropped"] or r["round"]["unknown"]:
        errors.append(f"a clean link reported drops: {r['round']}")

    # The cap.
    if r["capped"]["mine"] != 40 or r["capped"]["theirs"] != 1:
        errors.append(f"the 40-per-side cap did not hold: {r['capped']}")
    if r["capped"]["dropped"] < 20:
        errors.append(f"the ids past the cap were not counted: {r['capped']}")

    # An id on both sides.
    if r["both"]["mine"] != ["5", "6"] or r["both"]["theirs"] != ["7"] or r["both"]["both"] != 1:
        errors.append(f"an id on both sides was not kept on mine only: {r['both']}")

    # An id the engine no longer prices.
    if r["known"]["mine"] != ["5"] or r["known"]["theirs"] != ["7"] or r["known"]["unknown"] != 1:
        errors.append(f"an unknown id was not skipped and counted: {r['known']}")

    # size and the ticks.
    if r["sizes"] != [2, 2, 2, 4]:
        errors.append(f"size must be 2/3/4 (else 2): {r['sizes']}")
    if not r["flags"]["km"] or not r["flags"]["kt"]:
        errors.append(f"the lineup ticks must default on: {r['flags']}")
    if r["jumbled"]["mine"] != ["1"] or r["jumbled"]["theirs"] != ["2"]:
        errors.append(f"param order changed the rosters: {r['jumbled']}")
    return errors


class ShareLinksCodecTest(unittest.TestCase):
    def test_finder_link_codec(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "theirs never encoded": js.replace("if (theirs) parts.push(`theirs=${theirs}`);", "", 1),
            "the 40-per-side cap dropped": js.replace("if (out.length >= FINDER_MAX_SIDE) { dropped += 1; return; }", "", 1),
            "cross-side rule dropped": js.replace("const theirs = theirsAll.filter(k => !mineSet.has(k));", "const theirs = theirsAll;", 1),
            "bad size accepted": js.replace("size: MAX_SIZE_CHOICES.includes(size) ? size : 2", "size: Number.isFinite(size) ? size : 2", 1),
            "unknown ids kept": js.replace("if (known && !known.has(id)) { unknown += 1; return; }", "", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check_from(body), [], f"codec checks did not catch: {name}")


def check_from(body: str) -> list[str]:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "finder.js"
        p.write_text(body, encoding="utf-8")
        return check(p)


if __name__ == "__main__":
    unittest.main()
