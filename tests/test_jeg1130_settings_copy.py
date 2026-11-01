"""JEG-1130, slice 4: the approved PMM glossary outside the locked files (Jeremy, 2026-10-26, final naming).

  * Overrides retires "our methodology" and "our value" in its copy: the banner, the Use / Reset / Back
    buttons, the preset label, the basis notes and the intro say "the default DDF Value" (the wording #1185
    used in v2.js);
  * League names the reader's side "Your team" / "Your fit", not "Our" (Jeremy, 2026-10-30 6:29 PM CT, A);
  * copy refers to a generic player as "this player" or "they", never "he" (Jeremy, 2026-10-29 9:21 PM CT,
    audit decision 10, on JEG-1130): Overrides, the player-search empty states, the league levels note, the
    Waivers legend, the audit glossary rows and the values explainer's prose.

Only copy is checked: comments in the scripts don't count. v2.js and shell.html (locked by JEG-1137 and
JEG-1263), curve-widget.js and value-model.js (hot files) and values-fieldnotes.js (JEG-1265) are a later slice.
Discrimination: test_checks_fail_on_broken_builds restores each old string in a copy of the sources.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = ("app/v2/overrides.js", "app/v2/league.js", "app/v2/waivers.js", "app/v2/finder.js",
         "app/v2/audit-pie.js", "app/values-explainer/template.html")
COMMENT = re.compile(r"(?m)(^|\s)//.*$")
# A quoted copy string: "...", `...` or HTML text between tags. Comments are stripped first.
STRINGS = re.compile(r'"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`|>([^<>]+)<')

RETIRED = {
    "app/v2/overrides.js": [re.compile(r"\bour methodology\b", re.I), re.compile(r"“our value”|\"our value\"", re.I)],
    # Jeremy, 2026-10-30 6:29 PM CT (A): League says "Your team" / "Your fit" for the reader's side, not "Our".
    "app/v2/league.js": [re.compile(r"^Our$|\bOur (team|fit)\b")],
}
# A bare "Our" inside a template's ${...} (the summary columns and filter rules) isn't a whole copy string.
RETIRED_SOURCE = {"app/v2/league.js": [re.compile(r'"Our"')]}
HE = re.compile(r"\b(he|him|his)\b", re.I)
# Each must be present: the new wording, so a revert that drops the sentence also fails.
PRESENT = {
    "app/v2/overrides.js": ['{id: "default", text: "Default DDF Value"}', 'text: "Use the default DDF Value"',
                            'text: "Back to the default DDF Value."', "What DDF Value means on every tab."],
    "app/v2/league.js": ["Check the spelling, or this player may not have a value yet.", 'plainTh("Your team fit", two)',
                         "`Your fit: ${r.ours ?", '[["mine", "Your team"], ["theirs", "Their team"]]'],
    "app/v2/waivers.js": ["Check the spelling, or this player may not have a value yet."],
    "app/v2/finder.js": ["Check the spelling, or this player may not have a value yet."],
}


def copy_strings(path: str, text: str) -> list[str]:
    if path.endswith(".js"):
        text = COMMENT.sub(r"\1", text)
    else:
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return [next(g for g in m.groups() if g is not None) for m in STRINGS.finditer(text)]


def check(src: dict[str, str]) -> list[str]:
    errors = []
    for path, text in src.items():
        strings = copy_strings(path, text)
        for pattern in RETIRED.get(path, []):
            for s in strings:
                if pattern.search(s):
                    errors.append(f"{path} still says {pattern.pattern!r}: {s[:90]}")
        code = COMMENT.sub(r"\1", text) if path.endswith(".js") else text
        for pattern in RETIRED_SOURCE.get(path, []):
            for m in pattern.finditer(code):
                errors.append(f"{path} still says {m.group(0)}: {code[max(0, m.start() - 40):m.end() + 20]!r}")
        for s in strings:
            m = HE.search(s)
            if m and " " in s.strip():   # copy, not an identifier
                errors.append(f"{path} calls a generic player {m.group(0)!r}: {s[:90]}")
        for want in PRESENT.get(path, []):
            if want not in text:
                errors.append(f"{path} lost {want!r}")
    return errors


MUTANTS = {
    "Use our methodology": ("app/v2/overrides.js", 'text: "Use the default DDF Value"', 'text: "Use our methodology"'),
    "preset label": ("app/v2/overrides.js", 'text: "Default DDF Value"}', 'text: "Our methodology"}'),
    "fallback warning": ("app/v2/overrides.js", "so the default DDF Value is used until one returns.",
                         "so our methodology is used until one returns."),
    "our value in the intro": ("app/v2/overrides.js", "What DDF Value means on every tab.",
                               "What “our value” means on every tab."),
    "he in Overrides help": ("app/v2/overrides.js", "to set this player's value.", "to set his value."),
    "he in the search empty state": ("app/v2/finder.js", "or this player may not have a value yet.",
                                     "or he may not have a value yet."),
    "his in the league note": ("app/v2/league.js", "free agent at that position.", "free agent at his position."),
    "him in the Waivers legend": ("app/v2/waivers.js", "sources that price that player).", "sources that price him)."),
    "he in the audit glossary": ("app/v2/audit-pie.js", "starter if they would start,", "starter if he would start,"),
    "Our team fit column": ("app/v2/league.js", 'plainTh("Your team fit", two)', 'plainTh("Our team fit", two)'),
    "Our fit phone line": ("app/v2/league.js", "`Your fit: ${r.ours ?", "`Our fit: ${r.ours ?"),
    "Our team filter option": ("app/v2/league.js", '["mine", "Your team"]]', '["mine", "Our team"]]'),
    "Our summary column": ("app/v2/league.js", 'label: `${side === "mine" ? "Your" : "Their"}',
                           'label: `${side === "mine" ? "Our" : "Their"}'),
    "Our summary filter rule": ("app/v2/league.js", '${rule.side === "mine" ? "Your" : "Their"} team',
                                '${rule.side === "mine" ? "Our" : "Their"} team'),
    "his in the explainer": ("app/values-explainer/template.html", "and at that player's DDF Value.", "and at his DDF Value."),
}


class SettingsCopyGlossaryTests(unittest.TestCase):
    def sources(self):
        return {name: (ROOT / name).read_text(encoding="utf-8") for name in FILES}

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
