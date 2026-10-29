"""Waivers tab: an old Sleeper injury status never reads as current (JEG-1312).

The rows' injury_status comes from the Sleeper identity base the bake read. When that refresh stops (JEG-1238: no
successful run from Oct 15, so the live page shipped the Oct 9 copy), the tab must not print "Your Rex RunOne is Out"
or an Out tag from the old copy. The rule in app/v2/waivers.js:

  * statusFreshness(window.TradeValueStatus, now): shown only when the copy has a date and is at most
    STATUS_MAX_AGE_DAYS (6) old, with "Sleeper status as of <day>"; otherwise hidden, with the date and age said;
  * statusOf(row, freshness): the status a row may show, null when hidden or when the player has no status;
  * injuryNote / evaluateCandidate: no "Your X is Out" when the copy is hidden or the context has no status;
  * build_v2_page.player_status_js: the date is meta.universe.nfl_active.identity_base_pulled_at from players.json
    (the base the bake used), null when the file or the field is missing.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of waivers.js with one rule broken.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WAIVERS_JS = ROOT / "app" / "v2" / "waivers.js"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "pipelines"))

import build_v2_page  # noqa: E402

DAY = 24 * 60 * 60 * 1000
PULLED = "2026-10-09T18:46:05+00:00"
PULLED_MS = int(datetime.fromisoformat(PULLED).timestamp() * 1000)

PRELUDE = """
const fs = require('fs');
const W = require(process.argv[1]);
const F = require(process.argv[1].replace(/waivers\\.js$/, 'finder.js'));
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const charts = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
const row = p => ({player_key: p.key, name: p.name, pos: p.pos, team: p.team, notEvaluated: Boolean(p.notEvaluated),
  injury_status: (input.status || {})[p.name] || null,
  values: p.ddf === null ? {usatoday: p.market, fantasycalc: p.market, fantasypros: p.market, cbs: p.market}
    : {ddf_value: p.ddf, ddf_value_charts: p.ddf - p.noise, ddf_value_projections: p.ddf + p.noise, usatoday: p.market, fantasycalc: p.market, fantasypros: p.market, cbs: p.market}});
const out = (function () { %s })();
console.log(JSON.stringify(out));
"""

FRESHNESS = """
return input.cases.map(c => W.statusFreshness(c.status, c.now));
"""

STATUS_OF = """
const f = W.statusFreshness(input.tv, input.now);
return input.rows.map(r => W.statusOf(r, f));
"""

# One RB starter (Rex RunOne) marked Out; the RB candidates' reasons carry the injury note only when the copy is shown.
EVALUATE = """
const fx = input.fx;
const ctx = {shape: fx.shape, expected: F.expectedDepth(fx.alloc, fx.teams), chartKeys: charts, rosterSize: W.rosterSizeOf(fx.shape),
  weights: fx.weights};
if (input.tv !== undefined) ctx.status = W.statusFreshness(input.tv, input.now);
const c = W.evaluateAll(ctx, fx.roster.map(row), fx.candidates.map(row));
return c.results.map(r => ({name: r.name, reason: r.reason, injury: r.injury || null}));
"""


def node(js: Path, body: str, payload: dict):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    result = subprocess.run(["node", "-e", PRELUDE % body, str(js)], input=json.dumps(payload),
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def fixture() -> dict:
    return json.loads((FIXTURES / "waiver-thin-rb.json").read_text(encoding="utf-8"))


OUT_NOTE = "Your Rex RunOne is Out"


def check_rules(js: Path) -> list[str]:
    """Every rule above, as a list of failures (empty = all hold)."""
    errors = []
    tv = {"source": "Sleeper", "as_of": PULLED}
    cases = [
        {"status": tv, "now": PULLED_MS + 2 * DAY},                 # 0 fresh
        {"status": tv, "now": PULLED_MS + 20 * DAY},                # 1 the live case: 20 days old
        {"status": tv, "now": PULLED_MS + 6 * DAY},                 # 2 exactly at the limit: shown
        {"status": tv, "now": PULLED_MS + 6 * DAY + 60_000},        # 3 one minute past: hidden
        {"status": None, "now": PULLED_MS},                         # 4 no status file
        {"status": {"source": "Sleeper", "as_of": None}, "now": PULLED_MS},   # 5 no date
        {"status": {"source": "Sleeper", "as_of": "not a date"}, "now": PULLED_MS},  # 6 bad date
    ]
    got = node(js, FRESHNESS, {"cases": cases})
    if not (got[0]["shown"] and got[0]["label"] == "Sleeper status as of Oct 9" and got[0]["text"] == "Injury status: Sleeper, as of Oct 9."):
        errors.append(f"fresh copy (2 days) not shown with its date: {got[0]}")
    if got[1]["shown"]:
        errors.append(f"20-day-old copy is shown as current: {got[1]}")
    if got[1]["text"] != "Injury status is not shown: the latest Sleeper status is from Oct 9, 20 days old.":
        errors.append(f"stale copy does not say its date and age: {got[1]['text']!r}")
    if not got[2]["shown"]:
        errors.append(f"copy exactly 6 days old is hidden: {got[2]}")
    if got[3]["shown"]:
        errors.append(f"copy past 6 days is shown: {got[3]}")
    for i in (4, 5, 6):
        if got[i]["shown"] or "has no date" not in got[i]["text"]:
            errors.append(f"undated copy (case {i}) is shown or not explained: {got[i]}")

    rows = [{"injury_status": "Out"}, {"injury_status": "Active"}, {"injury_status": None}, {"injury_status": "Questionable"}]
    fresh = node(js, STATUS_OF, {"tv": tv, "now": PULLED_MS + DAY, "rows": rows})
    if fresh != ["Out", None, None, "Questionable"]:
        errors.append(f"fresh statusOf {fresh}, want ['Out', None, None, 'Questionable']")
    stale = node(js, STATUS_OF, {"tv": tv, "now": PULLED_MS + 20 * DAY, "rows": rows})
    if stale != [None, None, None, None]:
        errors.append(f"stale statusOf {stale}, want no status on any row")

    fx = fixture()
    status = {"Rex RunOne": "Out"}
    rb = [c["name"] for c in fx["candidates"] if c["pos"] == "RB"]
    shown = {r["name"]: r for r in node(js, EVALUATE, {"fx": fx, "status": status, "tv": tv, "now": PULLED_MS + DAY})}
    if not any(OUT_NOTE in shown[n]["reason"] for n in rb):
        errors.append("fresh copy: no RB candidate's reason carries the injury note (the positive control)")
    for label, payload in (("stale", {"tv": tv, "now": PULLED_MS + 20 * DAY}), ("no status in the context", {})):
        hidden = node(js, EVALUATE, {"fx": fx, "status": status, **payload})
        for r in hidden:
            if OUT_NOTE in r["reason"] or r["injury"]:
                errors.append(f"{label}: {r['name']}'s reason still says the old status: {r['reason']!r}")
    return errors


class TestWaiversStatus(unittest.TestCase):
    def test_stale_status_is_hidden_and_dated(self):
        self.assertEqual(check_rules(WAIVERS_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = WAIVERS_JS.read_text(encoding="utf-8")
        breaks = {
            "no age limit": ("if (ageDays > STATUS_MAX_AGE_DAYS) {", "if (false) {"),
            "note ignores freshness": ("if (!freshness || !freshness.shown) return null;", ""),
            "row ignores freshness": ("(freshness && freshness.shown && row", "(row"),
            "undated copy shown": ("if (!Number.isFinite(at) || !finite(nowMs)) {", "if (false) {"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy2(WAIVERS_JS.parent / "finder.js", Path(tmp) / "finder.js")
            for name, (old, new) in breaks.items():
                self.assertIn(old, source, name)
                broken = Path(tmp) / "waivers.js"
                broken.write_text(source.replace(old, new), encoding="utf-8")
                try:
                    failures = check_rules(broken)
                except subprocess.CalledProcessError:
                    failures = ["crashed"]
                self.assertTrue(failures, f"not caught: {name}")


class TestPlayerStatusJs(unittest.TestCase):
    def _js(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "players.json"
            if payload is not None:
                path.write_text(json.dumps(payload), encoding="utf-8")
            text = build_v2_page.player_status_js(path)
        prefix = "window.TradeValueStatus = "
        self.assertTrue(text.startswith(prefix) and text.endswith(";\n"), text)
        return json.loads(text[len(prefix):-2])

    def test_date_is_the_identity_base_the_bake_used(self):
        meta = {"meta": {"as_of": "2026-10-29", "universe": {"nfl_active": {"identity_base_pulled_at": PULLED}}}}
        self.assertEqual(self._js(meta), {"source": "Sleeper", "as_of": PULLED})

    def test_missing_file_or_date_gives_no_date(self):
        self.assertIsNone(self._js(None)["as_of"])
        self.assertIsNone(self._js({"meta": {"as_of": "2026-10-29"}})["as_of"])
        self.assertIsNone(self._js({"meta": {"universe": {"nfl_active": {"identity_base_pulled_at": ""}}}})["as_of"])

    def test_page_loads_the_status_before_the_tab(self):
        src = (ROOT / "pipelines" / "build_v2_page.py").read_text(encoding="utf-8")
        self.assertLess(src.index('src="v2/player-status.js"'), src.index('src="v2/waivers.js"'))
        self.assertIn('(out_dir / "player-status.js").write_text(player_status_js()', src)


if __name__ == "__main__":
    unittest.main()
