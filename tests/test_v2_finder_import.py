"""v2 Find a trade, second slice (JEG-481): league import parsers and roster sanity, in app/v2/finder.js.

  * Sleeper: rosters + users + the player directory become teams of {name, pos}; the team name is the owner's team name,
    else the display name; a roster player the directory does not know is dropped (never invented);
  * ESPN (public league): teams come with their players' full names and the position id as a position;
  * pasted names: one per line or comma-separated, notes in brackets dropped;
  * names are matched to the engine's rows ignoring case, punctuation and Jr/Sr/II; two players with one name are told
    apart by position, else left unmatched (never guessed); a name not in the values is reported, not added;
  * roster sanity: a trade is "thin" for a side when it leaves fewer players at QB/RB/WR/TE than the league starts and
    fewer than the side had, or fewer DDF starter-tier players than it had (short of the slots); a trade that was
    already short and does not get worse is not flagged; with the keep boxes on such trades are not listed;
  * findTrades with sanity: the keep flags drop thin trades and count them; with the flags off the trade is listed with
    its issues attached.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on mutated copies of finder.js.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

HARNESS = """
const F = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const out = F[input.fn](...input.args);
console.log(JSON.stringify(out));
"""


def call(finder_js, fn, *args):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, str(finder_js), json.dumps({"fn": fn, "args": list(args)})],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def player(key, name, pos, ddf=10, tier="starter", charts=10):
    return {"player_key": key, "name": name, "pos": pos, "ddfTier": tier,
            "values": dict(zip(["ddf_value"] + CH, [ddf] + [charts] * 4))}


SHAPE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}


def check(finder_js: Path) -> list[str]:
    errors = []
    # --- matching
    rows = [player("1", "Amon-Ra St. Brown", "WR"), player("2", "Kenneth Walker III", "RB"),
            player("3", "Josh Allen", "QB"), player("4", "Josh Allen", "LB"), player("5", "Patrick Mahomes", "QB")]
    got = call(finder_js, "matchNames", [{"name": "amon ra st brown", "pos": ""}, {"name": "Kenneth Walker", "pos": "RB"},
                                          {"name": "Josh Allen", "pos": "QB"}, {"name": "Patrick Mahomes II", "pos": ""},
                                          {"name": "Nobody Real", "pos": ""}], rows)
    keys = [r["player_key"] for r in got["matched"]]
    if keys != ["1", "2", "3", "5"]:
        errors.append(f"matched {keys}, want ['1', '2', '3', '5'] (case, punctuation, Jr/III and position are ignored when matching)")
    if [u["name"] for u in got["unmatched"]] != ["Nobody Real"]:
        errors.append(f"unmatched {got['unmatched']}: a name not in the values must be reported")
    got = call(finder_js, "matchNames", [{"name": "Josh Allen", "pos": ""}], rows)
    if got["matched"] or len(got["unmatched"]) != 1:
        errors.append("two players with one name and no position were guessed")
    got = call(finder_js, "matchNames", [{"name": "Patrick Mahomes", "pos": ""}, {"name": "Patrick Mahomes", "pos": ""}], rows)
    if len(got["matched"]) != 1:
        errors.append("a player listed twice was added twice")

    # --- parsers
    teams = call(finder_js, "parseSleeper",
                 [{"roster_id": 1, "owner_id": "u1", "players": ["100", "101", "999"]}, {"roster_id": 2, "owner_id": "u2", "players": ["102"]}],
                 [{"user_id": "u1", "display_name": "Jeremy", "metadata": {"team_name": "Gamblers"}}, {"user_id": "u2", "display_name": "Sam"}],
                 {"100": {"full_name": "Josh Allen", "position": "QB"}, "101": {"first_name": "Amon-Ra", "last_name": "St. Brown", "position": "WR"},
                  "102": {"full_name": "Patrick Mahomes", "position": "QB"}})
    if [t["label"] for t in teams] != ["Gamblers", "Sam"]:
        errors.append(f"sleeper team names {[t['label'] for t in teams]}, want team name else display name")
    if [e["name"] for e in teams[0]["entries"]] != ["Josh Allen", "Amon-Ra St. Brown"]:
        errors.append(f"sleeper entries {teams[0]['entries']}: an id the directory lacks must be dropped, a first/last name joined")
    teams = call(finder_js, "parseEspn", {"teams": [{"id": 3, "location": "Dallas", "nickname": "Dogs", "roster": {"entries": [
        {"playerPoolEntry": {"player": {"fullName": "CeeDee Lamb", "defaultPositionId": 3}}},
        {"playerPoolEntry": {"player": {"fullName": "Travis Kelce", "defaultPositionId": 4}}}, {"playerPoolEntry": {}}]}}]})
    if not teams or teams[0]["label"] != "Dallas Dogs" or [(e["name"], e["pos"]) for e in teams[0]["entries"]] != [("CeeDee Lamb", "WR"), ("Travis Kelce", "TE")]:
        errors.append(f"espn parse: {teams}")
    got = call(finder_js, "parsePasted", "Josh Allen (QB - BUF)\nAmon-Ra St. Brown, Kenneth Walker III\n\n")
    if [g["name"] for g in got] != ["Josh Allen", "Amon-Ra St. Brown", "Kenneth Walker III"]:
        errors.append(f"pasted names parsed as {got}")

    # --- roster sanity
    roster = [player("q1", "Q1", "QB"), player("r1", "R1", "RB"), player("r2", "R2", "RB"), player("w1", "W1", "WR"),
              player("w2", "W2", "WR"), player("t1", "T1", "TE")]
    # Giving a RB for a WR leaves 1 RB for 2 slots.
    issues = call(finder_js, "lineupIssues", roster, [roster[1]], [player("w9", "W9", "WR")], SHAPE)
    if [(i["pos"], i["have"], i["kind"]) for i in issues] != [("RB", 1, "count")]:
        errors.append(f"giving a RB for a WR should leave RB thin: {issues}")
    # RB for RB: fine.
    if call(finder_js, "lineupIssues", roster, [roster[1]], [player("r9", "R9", "RB")], SHAPE):
        errors.append("a like-for-like swap was flagged")
    # Already short (1 RB for 2 slots) and getting no worse: not flagged.
    short = [r for r in roster if r["player_key"] != "r2"]
    if call(finder_js, "lineupIssues", short, [short[3]], [player("w9", "W9", "WR")], SHAPE):
        errors.append("a side that was already short and did not get worse was flagged")
    # Giving a starter-tier RB for a bench RB: count unchanged, starter-tier shrinks below the slots.
    tiered = [dict(r, ddfTier="starter") for r in roster]
    issues = call(finder_js, "lineupIssues", tiered, [tiered[1]], [player("r9", "R9", "RB", tier="bench")], SHAPE)
    if [(i["pos"], i["kind"]) for i in issues] != [("RB", "starter")]:
        errors.append(f"trading a starter-tier RB for a bench RB should flag a starter loss: {issues}")
    # Roster as typed: no TE where the league starts one.
    gaps = call(finder_js, "rosterGaps", [r for r in roster if r["pos"] != "TE"], SHAPE)
    if [(g["pos"], g["have"], g["need"]) for g in gaps] != [("TE", 0, 1)]:
        errors.append(f"roster gap {gaps}")

    # --- the search honors the flags
    mine = [player("m1", "M1", "RB", ddf=20, charts=20), player("m2", "M2", "RB", ddf=5, charts=5), player("mq", "MQ", "QB", ddf=9, charts=9)]
    theirs = [player("t1", "T1", "WR", ddf=25, charts=18)]
    opts = {"maxSize": 1, "sanity": {"shape": {"RB": 2, "QB": 1, "WR": 0, "TE": 0}, "mine": mine, "theirs": theirs, "keepMine": True, "keepTheirs": False}}
    out = call(finder_js, "findTrades", mine, theirs, opts)
    if any(t["give"][0]["player_key"] == "m1" for t in out["trades"]) or not out["sanityDropped"]:
        errors.append(f"a trade that leaves my RBs short was listed with keepMine on: {out['trades']}")
    opts["sanity"]["keepMine"] = False
    out = call(finder_js, "findTrades", mine, theirs, opts)
    flagged = [t for t in out["trades"] if t["issues"]["mine"]]
    if not flagged or out["sanityDropped"]:
        errors.append(f"with keepMine off the thin trade must be listed with its issue: {out}")
    return errors


MUTANTS = {
    "case matters": ("const normName = name => String(name || \"\").toLowerCase()", "const normName = name => String(name || \"\")"),
    "ambiguous name guessed": ("if (hits.length !== 1) {", "if (hits.length === 0) {"),
    "sleeper unknown id kept": ("if (!p) return null;", "if (!p) return {name: String(id), pos: \"\"};"),
    "count rule ignores 'got worse'": ("if (all < need && all < before[pos].all)", "if (all < need)"),
    "starter rule dropped": ("else if (starters < Math.min(before[pos].starter, need))", "else if (false)"),
    "keep flag ignored": ("if ((sanity.keepMine && issues.mine.length) || (sanity.keepTheirs && issues.theirs.length))", "if (false)"),
    "paste notes kept": ("s.replace(/\\(.*?\\)/g, \"\")", "s"),
}


class FinderImportTests(unittest.TestCase):
    def test_import_and_sanity_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, source, f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
