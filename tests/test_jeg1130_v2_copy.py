"""JEG-1130, v2.js slice: the approved PMM glossary on the runtime strings (Jeremy, 2026-10-26, final naming).

  * the DDF Value and DDF Value (projections) definitions and tooltips name no publisher: OURS_DEFAULT (the
    default basis phrase every definition, footnote and series note is built from), the names popover entries,
    the series-row tips, the series-group note, the static spans the page rewrites, and the Overrides summary;
  * retired terms stay out of the copy: "positional weight inflation" (the Trade targets intro says "the positions
    the market overpays for", matching its H2), "Raw value above waivers", and "Movement" as the Risers info label;
  * the curve legend's line key says "Dashed = one chart of the Market" (desktop wording).

The JEG-1212 "Trade chart average" definition is pinned by test_v2_names_render and is not checked here.
Discrimination: test_checks_fail_on_broken_builds restores each old string in a copy of the sources.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.test_launch_copy_guard import PUBLISHERS

APP = Path(__file__).resolve().parents[1] / "app" / "v2"
FILES = ("v2.js", "shell.html", "overrides.js")
COMMENT = re.compile(r"(?m)(^|\s)//.*$")

# (file, regex whose group 1 is the copy): each must match, and none may name a publisher.
DEFINITIONS = {
    "OURS_DEFAULT": ("v2.js", r'const OURS_DEFAULT = "([^"]+)"'),
    "names popover DDF Value": ("v2.js", r'\["DDF Value", "([^"]+)"\]'),
    "names popover projections": ("v2.js", r'PROJECTIONS_DEF = \["DDF Value \(projections\)", "([^"]+)"\]'),
    "row tip ddf_value": ("v2.js", r'\bddf_value: "([^"]+)"'),
    "row tip ddf_value_charts": ("v2.js", r'\bddf_value_charts: "([^"]+)"'),
    "row tip ddf_value_projections": ("v2.js", r'\bddf_value_projections: "([^"]+)"'),
    "series group note": ("v2.js", r'note: "(DDF Value for each player:[^"]+)"'),
    "default row tip": ("v2.js", r'DDF_ROW_TIPS\.ddf_value = custom \? `[^`]+` : `([^`]+)`'),
    "Trade targets projections note": ("v2.js", r'basisPhrase\(\) : "([^"]+)"'),
    "shell basis span": ("shell.html", r"<span data-basis-ours>([^<]+)</span>"),
    "shell Trade targets note": ("shell.html", r'<span id="v2TOursNote">([^<]+)</span>'),
    "Overrides default summary": ("overrides.js", r'S\.mode === "default"\) return "([^"]+)"'),
}
RETIRED = [
    (re.compile(r"positional weight inflation", re.I), "positional weight inflation"),
    (re.compile(r"Raw value above waivers", re.I), "Raw value above waivers"),
    (re.compile(r'namesInfoButton\("Movement"\)'), "Movement as an info label"),
    (re.compile(r"our methodology", re.I), "our methodology"),
]
LEGEND = 'indexed: "Dashed = one chart of the Market"'


def check(src: dict[str, str]) -> list[str]:
    errors = []
    for name, (file, pattern) in DEFINITIONS.items():
        hits = re.findall(pattern, src[file])
        if not hits:
            errors.append(f"{name}: not found in {file}")
        for text in hits:
            m = PUBLISHERS.search(text)
            if m:
                errors.append(f"{name} names a publisher ({m.group(0)}): {text}")
    # Retired terms: copy only, so comments in the scripts don't count. Overrides keeps its other
    # "our methodology" strings for the Settings lane (JEG-1140), so that term is checked in v2.js and shell only.
    for file in ("v2.js", "shell.html"):
        text = COMMENT.sub(r"\1", src[file]) if file.endswith(".js") else re.sub(r"<!--.*?-->", "", src[file], flags=re.S)
        for pattern, label in RETIRED:
            if pattern.search(text):
                errors.append(f"{file} still says {label!r}")
    if LEGEND not in src["v2.js"]:
        errors.append("the curve legend key does not say \"Dashed = one chart of the Market\"")
    return errors


MUTANTS = {
    "publisher back in OURS_DEFAULT": ("v2.js", 'const OURS_DEFAULT = "rooted in the trade charts,',
                                       'const OURS_DEFAULT = "rooted in the trade charts FantasyCalc and CBS,'),
    "publisher in the projections definition": ("v2.js", '"The alternate: the projection sources, equal weight',
                                                '"The alternate: ESPN, CBS rest of season and Razzball projections, equal weight'),
    "publisher in the static basis span": ("shell.html", "<span data-basis-ours>rooted in the trade charts,",
                                           "<span data-basis-ours>rooted in the FantasyPros chart,"),
    "publisher in the Overrides summary": ("overrides.js", '"DDF Value = the default: rooted in the trade charts,',
                                           '"DDF Value = the default: rooted in the trade charts (USA Today),'),
    "old Trade targets intro": ("v2.js", "and the positions the market overpays for, position by position.",
                                "and potential positional weight inflation, position by position."),
    "old raw-vorp group title": ("v2.js", 'title: "Value above waivers (advanced)"', 'title: "Raw value above waivers (advanced)"'),
    "Movement info label": ("v2.js", 'namesInfoButton("Change")', 'namesInfoButton("Movement")'),
    "our methodology in the share note": ("v2.js", "switch back to the default DDF Value in one click",
                                          "switch back to our methodology in one click"),
    "old legend key": ("v2.js", LEGEND, "indexed: \"Dashed = rescaled chart\""),
}


class V2CopyGlossaryTests(unittest.TestCase):
    def sources(self):
        return {name: (APP / name).read_text(encoding="utf-8") for name in FILES}

    def test_glossary(self):
        self.assertEqual(check(self.sources()), [])

    def test_checks_fail_on_broken_builds(self):
        for name, (target, old, new) in MUTANTS.items():
            with self.subTest(name):
                s = self.sources()
                self.assertIn(old, s[target], f"mutant {name!r} no longer applies")
                s[target] = s[target].replace(old, new, 1)
                self.assertTrue(check(s), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
