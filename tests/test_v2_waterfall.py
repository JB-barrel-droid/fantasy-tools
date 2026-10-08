"""v2 Compare a trade: waterfall steps, verdict and example trade in app/v2/trade.js.

JEG-468 / JEG-469. These are pure helpers; the page only draws what they return.
The checks pin:

  * waterfall: give steps first, largest first, each moving the running total
    down by exactly that player's value; then receive steps, largest first, up;
    the net is today's Receive − give (compareTrade's own sums); lo / hi are the
    cumulative extent with 0 included;
  * a player without a value is a "missing" step that moves nothing, every
    later step is marked partial, and the row has no net (never a 0);
  * waterfallScale: the largest cumulative extent across rows, not the largest net;
  * tradeVerdict: one series decides win / lose / even; the complete series
    that point the other way are "against"; incomplete rows never count; a
    missing verdict series is "incomplete";
  * pickExample: a 2-for-2 from fully priced players that the verdict series
    calls a win, preferring one the most other series call a loss; deterministic.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on
mutated copies (missing read as 0, smallest first, scale from the net only,
incomplete rows counted in the verdict, against / agree swapped, example that
ignores the other series) and requires each to fail.
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
const strip = w => ({...w, steps: w.steps.map(s => ({...s, row: s.row.player_key}))});
const falls = input.falls.map(([give, receive, key]) => strip(T.waterfall(give, receive, key)));
const scale = T.waterfallScale(input.scaleRows.map(([give, receive, key]) => T.waterfall(give, receive, key)));
const verdicts = input.verdicts.map(([rows, key]) => { const v = T.tradeVerdict(rows, key);
  return {kind: v.kind, againstKeys: v.againstKeys || null, agreeKeys: v.agreeKeys || null, incompleteKeys: v.incompleteKeys || null}; });
const ex = T.pickExample(input.example.rows, input.example.keys, input.example.key);
const again = T.pickExample(input.example.rows, input.example.keys, input.example.key);
console.log(JSON.stringify({falls, scale, verdicts,
  example: ex && {give: ex.give.map(r => r.player_key), receive: ex.receive.map(r => r.player_key)},
  exampleAgain: again && {give: again.give.map(r => r.player_key), receive: again.receive.map(r => r.player_key)}}));
"""


def p(key, **values):
    return {"player_key": key, "name": f"P{key}", "values": values}


A, B, C, D = p(1, x=10.0, y=3.0), p(2, x=25.0, y=None), p(3, x=12.0, y=4.0), p(4, x=30.0, y=1.0)
FALLS = [([A, B], [C, D], "x"), ([A, B], [C, D], "y"), ([A], [C], "x")]
# Row 1 nets small (+7) but runs down to −35: the scale is the cumulative extent.
SCALE_ROWS = [([A, B], [C, D], "x"), ([A], [D], "x")]


def vrow(key, net):
    return {"key": key, "net": net}


VERDICTS = [
    ([vrow("x", 6.2), vrow("a", -2.0), vrow("b", 3.0), vrow("c", None), vrow("d", -0.01)], "x"),   # win, a against, c not counted
    ([vrow("x", -3.1), vrow("a", 2.0), vrow("b", -1.0)], "x"),                                     # lose, a against
    ([vrow("x", None), vrow("a", 2.0)], "x"),                                                       # incomplete
    ([vrow("x", 4.0), vrow("a", 1.0), vrow("b", 2.0)], "x"),                                        # every source agrees
    ([vrow("x", 0.02), vrow("a", 1.0)], "x"),                                                       # 0.0 = even
]
WANT_VERDICTS = [
    {"kind": "win", "againstKeys": ["a"], "agreeKeys": ["b"], "incompleteKeys": ["c"]},
    {"kind": "lose", "againstKeys": ["a"], "agreeKeys": ["b"], "incompleteKeys": []},
    {"kind": "incomplete", "againstKeys": [], "agreeKeys": [], "incompleteKeys": []},
    {"kind": "win", "againstKeys": [], "agreeKeys": ["a", "b"], "incompleteKeys": []},
    {"kind": "even", "againstKeys": [], "agreeKeys": [], "incompleteKeys": []},
]
# Example pool: k decides; o disagrees with k on players 5 and 6.
POOL = [p(1, k=50, o=50), p(2, k=40, o=40), p(3, k=30, o=30), p(4, k=20, o=20),
        p(5, k=19, o=5), p(6, k=18, o=4), p(7, k=None, o=99)]


def run(trade_js: Path):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    payload = {"falls": FALLS, "scaleRows": SCALE_ROWS, "verdicts": VERDICTS,
               "example": {"rows": POOL, "keys": ["k", "o"], "key": "k"}}
    out = subprocess.run(["node", "-e", HARNESS, str(trade_js), json.dumps(payload)],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def close(a, b):
    return a is not None and b is not None and abs(a - b) < 1e-9


def check(trade_js: Path) -> list[str]:
    errors = []
    try:
        got = run(trade_js)
    except subprocess.CalledProcessError as exc:
        return [f"harness failed: {exc.stderr[:300]}"]
    full, gap, single = got["falls"]
    # Complete row: give 25 then 10 (largest first) down, receive 30 then 12 up.
    want = [("give", 2, -25.0, -25.0), ("give", 1, -10.0, -35.0), ("receive", 4, 30.0, -5.0), ("receive", 3, 12.0, 7.0)]
    have = [(s["side"], s["row"], s["delta"], s["running"]) for s in full["steps"]]
    if len(have) != 4 or any(h[:2] != w[:2] or not close(h[2], w[2]) or not close(h[3], w[3]) for h, w in zip(have, want)):
        errors.append(f"complete waterfall steps {have} != {want}")
    if not close(full["net"], 7.0) or not full["complete"]:
        errors.append(f"complete waterfall net {full['net']} != receive − give 7.0")
    if not (close(full["lo"], -35.0) and close(full["hi"], 7.0)):
        errors.append(f"extent {full['lo']}..{full['hi']} != -35..7")
    # Missing: player 2 has no y. A missing step, nothing moves, later steps partial, no net.
    miss = [s for s in gap["steps"] if s["missing"]]
    if len(miss) != 1 or miss[0]["row"] != 2 or miss[0]["delta"] is not None or miss[0]["start"] != miss[0]["end"]:
        errors.append(f"missing step wrong: {miss}")
    if gap["net"] is not None or gap["complete"]:
        errors.append(f"incomplete waterfall has a net: {gap['net']}")
    later = [s for s in gap["steps"] if s["side"] == "receive"]
    if not later or not all(s["partial"] for s in later):
        errors.append("steps after a missing value are not marked partial")
    if not close(single["net"], 2.0):
        errors.append(f"1-for-1 net {single['net']} != 2.0")
    if not (close(got["scale"]["lo"], -35.0) and close(got["scale"]["hi"], 20.0)):
        errors.append(f"shared scale {got['scale']} != cumulative extent -35..20")
    for i, (have, want) in enumerate(zip(got["verdicts"], WANT_VERDICTS)):
        if have != want:
            errors.append(f"verdict {i}: {have} != {want}")
    ex = got["example"]
    if not ex or len(ex["give"]) != 2 or len(ex["receive"]) != 2 or 7 in ex["give"] + ex["receive"]:
        errors.append(f"example is not a fully priced 2-for-2: {ex}")
    else:
        k = {r["player_key"]: r["values"] for r in POOL}
        net = lambda s: sum(k[i][s] for i in ex["receive"]) - sum(k[i][s] for i in ex["give"])
        if not net("k") >= 1 or not net("o") < 0:
            errors.append(f"example should win by k and lose by o: k {net('k')} o {net('o')} ({ex})")
    if got["exampleAgain"] != ex:
        errors.append("example is not deterministic")
    return errors


class WaterfallVerdictTest(unittest.TestCase):
    def test_waterfall_verdict_example(self):
        self.assertEqual(check(TRADE_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        broken = {
            "missing read as zero": source.replace(
                "const valueOf = row => (row.values ? row.values[key] : null);",
                "const valueOf = row => (row.values ? row.values[key] : null) ?? 0;", 1),
            "smallest first": source.replace("priced.sort((a, b) => b.value - a.value || a.i - b.i);",
                                             "priced.sort((a, b) => a.value - b.value || a.i - b.i);", 1),
            "scale from the net only": source.replace(
                "const marks = [0].concat(...steps.map(s => [s.start, s.end]), sums.net === null ? [] : [sums.net]);",
                "const marks = [0].concat(sums.net === null ? [] : [sums.net]);", 1),
            "incomplete rows counted in the verdict": source.replace(
                "const complete = others.filter(row => row.net !== null);\n    const incompleteKeys",
                "const complete = others.map(row => (row.net === null ? {...row, net: -1} : row));\n    const incompleteKeys", 1),
            "against and agree swapped": source.replace(
                "const againstKeys = s > 0 ? base.downKeys : s < 0 ? base.upKeys : [];",
                "const againstKeys = s > 0 ? base.upKeys : s < 0 ? base.downKeys : [];", 1),
            "example ignores the other series": source.replace(
                "const score = [v.againstKeys.length, -v.net];", "const score = [0, -v.net];", 1),
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
