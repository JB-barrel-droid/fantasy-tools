"""JEG-510 (Jeremy, GL-21, 2026-10-09): the published trade charts are labeled
"rescaled" for the numeric transformation, never "as published" or "indexed".
JEG-1212 changes "Published charts" into a source category, so that phrase is
now allowed while the transformation label still says rescaled.

Scans the user-facing strings of app/v2 (shell.html text and attributes, plus
the string literals of the v2 scripts). Internal keys and method ids stay
`indexed` (the bare literal "indexed", `is-indexed` classes, data-* ids); only
copy is checked. test_guard_fails_on_old_labels restores each old label in turn
and requires the scan to flag it.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

V2 = Path(__file__).resolve().parents[1] / "app" / "v2"
SCRIPTS = ("v2.js", "targets.js", "movers.js", "trade.js", "finder.js", "modules.js")

BANNED = [
    (re.compile(r"as[ -]published", re.I), "as published"),
    # "indexed" as a word, not a css class / id (is-indexed, data-sources="indexed")
    (re.compile(r"(?<![-\w.#])indexed(?![-\w])", re.I), "indexed"),
    (re.compile(r"(?<![-\w.#])Index(?![-\w])"), "Index"),
]

STRING_LITERAL = re.compile(r'"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`')
LINE_COMMENT = re.compile(r"(?m)(^|\s)//.*$")
BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def _hits(text: str) -> list[str]:
    found = []
    for pattern, label in BANNED:
        if pattern.search(text):
            found.append(f"{label!r} in {text[:80]!r}")
    return found


def script_copy_violations(source: str) -> list[str]:
    source = LINE_COMMENT.sub(r"\1", BLOCK_COMMENT.sub("", source))
    violations = []
    for match in STRING_LITERAL.finditer(source):
        literal = match.group(1) if match.group(1) is not None else match.group(2)
        if literal == "indexed":  # the internal method id
            continue
        violations += _hits(literal)
    return violations


def shell_copy_violations(html: str) -> list[str]:
    html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    html = re.sub(r"<(script|style)\b.*?</\1>", "", html, flags=re.S)
    violations = []
    for attr in re.findall(r'\b(?:aria-label|title|placeholder|alt)="([^"]*)"', html):
        violations += _hits(attr)
    violations += _hits(re.sub(r"<[^>]+>", " ", html))
    return violations


def all_violations(scripts: dict[str, str], shell: str) -> list[str]:
    out = [f"shell.html: {v}" for v in shell_copy_violations(shell)]
    for name, source in scripts.items():
        out += [f"{name}: {v}" for v in script_copy_violations(source)]
    return out


def _load():
    scripts = {name: (V2 / name).read_text(encoding="utf-8") for name in SCRIPTS}
    return scripts, (V2 / "shell.html").read_text(encoding="utf-8")


class RescaledCopyTest(unittest.TestCase):
    def test_no_old_labels_in_v2_copy(self):
        scripts, shell = _load()
        self.assertEqual(all_violations(scripts, shell), [])

    def test_agreed_labels_present(self):
        scripts, shell = _load()
        v2 = scripts["v2.js"]
        self.assertIn('title: "Published charts"', v2)
        self.assertIn('["published", "Published charts"]', v2)
        self.assertIn('title: "Observed-trade estimates"', v2)
        self.assertIn("chart (rescaled)", v2)
        self.assertIn(
            "Published trade-value opinions. Rescaled series use our point scale for your league; "
            "adjusted series follow their own label.", v2)

    def test_scale_anchor_not_described(self):
        # JEG-499: do not say whether the scale is ESPN- or DDF-anchored until it is settled.
        scripts, shell = _load()
        v2 = scripts["v2.js"]
        info = re.search(r"const INDEXED_INFO = (.*?);\n", v2, re.S).group(1)
        self.assertNotRegex(info, r"ESPN|DDF")

    def test_guard_fails_on_old_labels(self):
        scripts, shell = _load()
        v2 = scripts["v2.js"]
        broken = {
            "group title": ("v2.js", 'title: "Published charts"', 'title: "Trade charts (as published)"'),
            "series name": ("v2.js", "chart (rescaled${RESCALED_TO})`,\n      observed", "chart (as published)`,\n      observed"),
            # JEG-1119 (Jeremy, 2026-10-26): the method labels read "Market"; the anchors follow, the mutations do not.
            "column label": ("v2.js", 'PLAIN_METHOD = {dda: "DDF Value", indexed: "Market", vorp', 'PLAIN_METHOD = {dda: "DDF Value", indexed: "As published", vorp'),
            "short label": ("v2.js", 'SHORT_METHOD = {dda: "DDF Value", indexed: "Market", vorp', 'SHORT_METHOD = {dda: "DDF Value", indexed: "Index", vorp'),
            "target sub-label": ("v2.js", '" · " : ""}rescaled`', '" · " : ""}indexed`'),
            "info title": ("v2.js", 'title: "Rescaled values"', 'title: "Indexed values"'),
            "legend": ("v2.js", 'indexed: `Dashed = rescaled chart${RESCALED_TO}`', 'indexed: "Dashed = as published chart"'),
        }
        for name, (_file, old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertIn(old, v2, f"mutation anchor for {name!r} is stale")
                mutated = dict(scripts, **{"v2.js": v2.replace(old, new, 1)})
                self.assertNotEqual(all_violations(mutated, shell), [], f"scan missed: {name}")
        with self.subTest(mutation="shell pill"):
            old = '<span class="v2-pill is-indexed">Rescaled</span>'
            self.assertIn(old, shell)
            self.assertNotEqual(
                all_violations(scripts, shell.replace(old, '<span class="v2-pill is-indexed">Indexed</span>', 1)), [])


if __name__ == "__main__":
    unittest.main()
