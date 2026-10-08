"""v2 Compare a trade: side totals and the trade story in app/v2/trade.js.

Frame 07 puts "<series> total" under each side; frame 22 #15 tells the trade
story from complete rows only. These checks pin:

  * sideTotal: the sum of one series over one side; any player without a value
    makes the total incomplete (null plus who is missing), never a 0;
  * tradeStory "contrast": one publisher's Data Driven Adjustments and Indexed
    nets point opposite ways, in the same week;
  * no contrast when the two weeks differ (different snapshots), or when a net
    shows as 0.0;
  * "agree" when every complete row points the same way, "split" when they
    point different ways, "incomplete" when no row is complete; VORP vs waivers
    rows never make a same-publisher contrast.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on
mutated copies (missing read as 0 in a total, week check dropped, contrast on
same signs, incomplete rows counted) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE_JS = ROOT / "app" / "v2" / "trade.js"

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const meta = key => input.meta[key];
const out = {
  totals: input.totals.map(([rows, key]) => { const t = T.sideTotal(rows, key);
    return {total: t.total, missing: t.missing.map(r => r.player_key)}; }),
  stories: input.stories.map(rows => { const s = T.tradeStory(rows, meta);
    return {kind: s.kind, publisher: s.publisher || null, up: s.up ?? null, down: s.down ?? null,
      upKeys: s.upKeys || null, downKeys: s.downKeys || null}; })
};
console.log(JSON.stringify(out));
"""

META = {
    "fantasycalc_adjusted": {"publisher": "fantasycalc", "method": "dda", "week": 5},
    "fantasycalc": {"publisher": "fantasycalc", "method": "indexed", "week": 5},
    "espn": {"publisher": "espn", "method": "dda", "week": 5},
    "espn_vorp": {"publisher": "espn", "method": "vorp", "week": 5},
    "cbs_adjusted": {"publisher": "cbs", "method": "dda", "week": 4},
    "cbs": {"publisher": "cbs", "method": "indexed", "week": 3},
}
A = {"player_key": 1, "values": {"espn": 30.0, "usatoday": 0.0}}
B = {"player_key": 2, "values": {"espn": 12.5, "usatoday": None}}


def row(key, net):
    return {"key": key, "net": net, "give": None if net is None else 0, "receive": None if net is None else net}


TOTALS = [([A, B], "espn"), ([A, B], "usatoday"), ([A], "usatoday"), ([], "espn")]
STORIES = [
    [row("fantasycalc_adjusted", 4.8), row("fantasycalc", -4.0), row("espn", 14.3)],      # contrast
    [row("cbs_adjusted", 3.0), row("cbs", -2.0), row("espn", 1.0)],                         # weeks differ: split
    [row("espn", 3.0), row("fantasycalc", 2.0), row("fantasycalc_adjusted", None)],         # agree (incomplete ignored)
    [row("espn", None), row("fantasycalc", None)],                                          # incomplete
    [row("fantasycalc_adjusted", 0.02), row("fantasycalc", -3.0), row("espn", -1.0)],       # 0.0 is no direction
    [row("espn", 2.0), row("espn_vorp", -9.0)],                                             # VORP is no contrast
    [row("fantasycalc_adjusted", 2.0), row("fantasycalc", 3.0), row("espn", 1.0)],          # same publisher agrees
]
WANT_TOTALS = [{"total": 42.5, "missing": []}, {"total": None, "missing": [2]},
               {"total": 0.0, "missing": []}, {"total": None, "missing": []}]
WANT_STORIES = [("contrast", "fantasycalc"), ("split", None), ("agree", None), ("incomplete", None),
                ("split", None), ("split", None), ("agree", None)]


def run(trade_js: Path):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    payload = {"meta": META, "totals": TOTALS, "stories": STORIES}
    out = subprocess.run(["node", "-e", HARNESS, str(trade_js), json.dumps(payload)],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def check(trade_js: Path) -> list[str]:
    errors = []
    try:
        got = run(trade_js)
    except subprocess.CalledProcessError as exc:
        return [f"harness failed: {exc.stderr[:300]}"]
    for i, (have, want) in enumerate(zip(got["totals"], WANT_TOTALS)):
        if have != want:
            errors.append(f"total {i}: {have} != {want}")
    for i, (have, (kind, publisher)) in enumerate(zip(got["stories"], WANT_STORIES)):
        if have["kind"] != kind or (publisher and have["publisher"] != publisher):
            errors.append(f"story {i}: {have} != {kind} {publisher or ''}")
    split = got["stories"][1]
    if (split["upKeys"], split["downKeys"]) != (["cbs_adjusted", "espn"], ["cbs"]):
        errors.append(f"split story names the wrong series per side: {split}")
    if got["stories"][2]["up"] != 2:
        errors.append(f"agree story counts only complete rows: {got['stories'][2]}")
    return errors


class TradeStoryTest(unittest.TestCase):
    def test_totals_and_story(self):
        self.assertEqual(check(TRADE_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        broken = {
            "missing read as zero in a total": source.replace(
                "if (!rows.length || missing.length) return {key, total: null, missing};",
                "if (!rows.length) return {key, total: null, missing};", 1).replace(
                "return {key, total: rows.reduce((sum, row) => sum + row.values[key], 0), missing};",
                "return {key, total: rows.reduce((sum, row) => sum + (row.values[key] || 0), 0), missing};", 1),
            "week check dropped": source.replace(
                "if (!pair.dda || !pair.indexed || pair.dda.week !== pair.indexed.week) continue;",
                "if (!pair.dda || !pair.indexed) continue;", 1),
            "contrast on same signs": source.replace("if (a && b && a !== b) return", "if (a && b) return", 1),
            "series sides swapped": source.replace(
                "    const upKeys = keysWhere(1);\n    const downKeys = keysWhere(-1);",
                "    const upKeys = keysWhere(-1);\n    const downKeys = keysWhere(1);", 1),
            "incomplete rows counted": source.replace(
                "const complete = rows.filter(row => row.net !== null);",
                "const complete = rows.map(row => (row.net === null ? {...row, net: 0} : row));", 1),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in broken.items():
                with self.subTest(mutation=name):
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                    path = Path(tmp) / f"{name.replace(' ', '_')}.js"
                    path.write_text(body, encoding="utf-8")
                    self.assertNotEqual(check(path), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
