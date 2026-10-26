"""JEG-1081 PR 7: canonical names and plain copy for the three views across the trade tools (spec v2 4a to 4c, 5b). String checks.

  * names: no user-visible string in the trade tools says "Trade chart avg", "Fundamentals", "fundamental evaluation" or the
    retired "DDF Projections"; code comments are not user-visible and are not scanned;
  * fit tooltips: every fit variant has its own plain sentence that names what backs the trade; an unknown variant reads as force;
  * the view tooltips (spec 4c) are the exact sentences, and under a basis of the reader's own the DDF Value tooltip says it is not
    our methodology and the market tooltip says "Rescaled to <basis>'s point scale" (spec 5b).

Discrimination: test_checks_fail_on_broken_builds puts each retired name back (and drops a tooltip clause) in copies of the sources.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call

APP = FINDER_JS.parent
FILES = sorted(p.name for p in APP.glob("*.js") if not p.name.startswith("audit-"))
RETIRED = re.compile(r"Trade chart avg(?!erage)|(?<!\w)Fundamentals?\b(?! of)|fundamental evaluation|DDF Projections", re.I)


def strings_of(source: str):
    """The text of every line that is code, not a comment (a line starting with // or inside a block comment is skipped)."""
    in_block = False
    for number, line in enumerate(source.split("\n"), 1):
        stripped = line.strip()
        if in_block:
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("/*"):
            in_block = "*/" not in stripped
            continue
        if stripped.startswith("//"):
            continue
        code = re.sub(r"\s//\s.*$", "", line) if re.search(r"\s//\s", line) and line.count('"') % 2 == 0 and line.count("`") % 2 == 0 else line
        yield number, code


def check(sources: dict[str, str], finder_js: Path) -> list[str]:
    errors = []
    say = errors.append
    for name, source in sources.items():
        for number, code in strings_of(source):
            m = RETIRED.search(code)
            if m:
                say(f"{name}:{number} still says {m.group(0)!r}: {code.strip()[:100]}")
    tips = {v: call(finder_js, "fitTip", v) for v in ("natural", "natural-charts", "natural-projections", "value", "force")}
    if len(set(tips.values())) != 5:
        say(f"fit tooltips are not five different sentences: {tips}")
    if "DDF Value (projections)" not in tips["natural-charts"] or "does not back it" not in tips["natural-charts"]:
        say(f"charts-only tooltip does not say the projections disagree: {tips['natural-charts']!r}")
    if "DDF Value does not" not in tips["natural-projections"]:
        say(f"projections-only tooltip does not say DDF Value disagrees: {tips['natural-projections']!r}")
    if call(finder_js, "fitTip", "nonsense") != tips["force"]:
        say("an unknown fit variant should read as force")
    default = {i: call(finder_js, "viewTip", i, {"isDefault": True}) for i in ("ddf", "market", "projections")}
    if default["ddf"] != "Our methodology: the four trade charts (FantasyCalc, USA Today, FantasyPros, CBS), adjusted for your league's position weights." \
            or default["market"] != "What the market pays: the same four trade charts, uniformly rescaled (no position weighting). The common language for trade proposals." \
            or default["projections"] != "The alternate: ESPN, CBS rest-of-season and Razzball projections, averaged for your league. Independent of the trade market.":
        say(f"the view tooltips are not the spec's sentences: {default}")
    single = {"isDefault": False, "mode": "single", "label": "FantasyCalc"}
    blend = {"isDefault": False, "mode": "blend", "label": "60% ESPN + 40% Razzball"}
    if "not our methodology" not in call(finder_js, "viewTip", "ddf", single) or "FantasyCalc" not in call(finder_js, "viewTip", "ddf", single):
        say("under the reader's own basis the DDF Value tooltip does not say it is not our methodology")
    if not call(finder_js, "viewTip", "market", single).endswith("Rescaled to FantasyCalc's point scale."):
        say(f"market tooltip under a single-source basis: {call(finder_js, 'viewTip', 'market', single)!r}")
    if not call(finder_js, "viewTip", "market", blend).endswith("Rescaled to the point scale of 60% ESPN + 40% Razzball."):
        say(f"market tooltip under a blend basis: {call(finder_js, 'viewTip', 'market', blend)!r}")
    if call(finder_js, "viewTip", "projections", single) != default["projections"]:
        say("the projections tooltip should not change with the basis")
    return errors


MUTANTS = {
    "chip says avg": ("finder.js", 'charts ? "Trade chart average" : "Trade chart average (too few charts)"', 'charts ? "Trade chart avg" : "Trade chart avg (too few charts)"'),
    "capture says fundamentals": ("opportunities.js", 'label: "DDF Value capture"', 'label: "Fundamentals capture"'),
    "waivers note says fundamental": ("waivers.js", "The DDF Value evaluation is unaffected.", "The fundamental evaluation is unaffected."),
    "card says fundamentals": ("league.js", "`DDF Value: ${signed(r.edge)} pts", "`Fundamentals: ${signed(r.edge)} pts"),
    "market tooltip without the rescaling": ("finder.js", "return `${VIEW_TIPS.market} Rescaled to ${basis.mode", "return `${VIEW_TIPS.market}${basis.mode"),
    "DDF Value tooltip ignores the basis": ("finder.js", 'if (id === "ddf" && custom) return', 'if (false) return'),
    "caption says fundamentals": ("league.js", "ranked by fit then by DDF Value capture", "ranked by fit then by fundamentals capture"),
    "tooltip ignores the variant": ("finder.js", "const fitTip = variant => FIT_TIPS[variant] || FIT_TIPS.force;", "const fitTip = variant => FIT_TIPS.natural;"),
}


class CopyNamesTests(unittest.TestCase):
    def test_copy(self):
        sources = {name: (APP / name).read_text(encoding="utf-8") for name in FILES}
        self.assertEqual(check(sources, FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        sources = {name: (APP / name).read_text(encoding="utf-8") for name in FILES}
        for name, (target, old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, sources[target], f"mutant {name!r} no longer applies")
                broken = {**sources, target: sources[target].replace(old, new, 1)}
                with tempfile.TemporaryDirectory() as tmp:
                    for fname in ("finder.js",):
                        (Path(tmp) / fname).write_text(broken[fname], encoding="utf-8")
                    self.assertTrue(check(broken, Path(tmp) / "finder.js"), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
