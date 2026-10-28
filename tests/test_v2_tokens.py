"""JEG-1136: the v2 design tokens (docs/design/2026-10-direction.md "Tokens") exist in v2.css for light and dark,
the type scale is 34/28/20/14/12 and nothing else, the token block has no !important, and every text/tint pair
passes WCAG AA (4.5:1) in both modes.

Discrimination: test_checks_fail_on_broken_css drops a dark role, adds a sixth type size, adds !important to the
block, and lowers a pair's contrast, and requires the checks to fail on each.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "app" / "v2" / "v2.css"
ROLES = ["canvas", "surface", "line", "ink", "muted", "action", "action-ink",
         "good-tint", "good-ink", "warn-tint", "warn-ink", "bad-tint", "bad-ink", "info-tint", "info-ink"]
PAIRS = [("ink", "surface"), ("muted", "surface"), ("action-ink", "action"),
         ("good-ink", "good-tint"), ("warn-ink", "warn-tint"), ("bad-ink", "bad-tint"), ("info-ink", "info-tint"),
         ("neutral-ink", "neutral-tint")]
SCALE = {"answer": 34, "emoji": 28, "name": 20, "body": 14, "meta": 12}


def block(css: str) -> str:
    start = css.index("/* JEG-1136: design tokens")
    return css[start:css.index("body.v2 { margin: 0;", start)]


def declarations(text: str) -> dict[str, str]:
    return dict(re.findall(r"(--ddf-[a-z0-9-]+):\s*([^;]+);", text))


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def check(css: str) -> list[str]:
    errors = []
    tokens = block(css)
    if "!important" in tokens:
        errors.append("the token block uses !important")
    parts = re.split(r"@media \(prefers-color-scheme: dark\)", tokens, maxsplit=1)
    light = declarations(parts[0].split(':root[data-canvas="paper"]')[0])
    dark_media = declarations(parts[1].split(':root[data-canvas="paper"]:not')[0])
    dark_attr = declarations(parts[1].split(':root[data-theme="dark"] {')[1].split("}")[0])
    for role in ROLES:
        if f"--ddf-{role}" not in light:
            errors.append(f"light --ddf-{role} missing")
    for role in ("ink", "muted", "action", "action-ink", "good-tint", "good-ink", "warn-tint", "warn-ink", "bad-tint", "bad-ink", "info-tint", "info-ink"):
        for name, dark in (("media", dark_media), ("attribute", dark_attr)):
            if f"--ddf-{role}" not in dark:
                errors.append(f"dark ({name}) --ddf-{role} missing")
    if dark_media != dark_attr:
        errors.append("the dark media-query values differ from the data-theme=dark values")
    for name, px in SCALE.items():
        if light.get(f"--ddf-type-{name}") != f"{px}px":
            errors.append(f"type scale {name} is {light.get(f'--ddf-type-{name}')}, want {px}px")
    extra = [k for k in light if k.startswith("--ddf-type-") and k[len("--ddf-type-"):] not in SCALE]
    if extra:
        errors.append(f"type sizes outside the scale: {extra}")
    # Canvas and surface follow the legacy --v2-* values (today's cool set), so their literals are read from there.
    modes = {"light": {**light, "--ddf-surface": "#FFFFFF"}, "dark": {**light, **dark_attr, "--ddf-surface": "#15211D"}}
    for mode, values in modes.items():
        for fg, bg in PAIRS:
            f, b = values.get(f"--ddf-{fg}", ""), values.get(f"--ddf-{bg}", "")
            if not (f.startswith("#") and b.startswith("#")):
                errors.append(f"{mode}: {fg}/{bg} are not literal colors ({f!r}, {b!r})")
            elif contrast(f, b) < 4.5:
                errors.append(f"{mode}: {fg} on {bg} is {contrast(f, b):.2f}:1, below AA 4.5")
    if not (light.get("--ddf-radius-card") == "12px" and light.get("--ddf-hit") == "44px" and light.get("--ddf-page-pad-phone") == "16px"):
        errors.append("radius 12 / hit target 44 / phone padding 16 tokens changed")
    return errors


class TokenTests(unittest.TestCase):
    def test_tokens(self):
        self.assertEqual(check(CSS.read_text(encoding="utf-8")), [])

    def test_checks_fail_on_broken_css(self):
        css = CSS.read_text(encoding="utf-8")
        broken = {
            "dark role dropped": css.replace("--ddf-bad-ink: #F2A3AE; ", "", 2),
            "sixth type size": css.replace("--ddf-type-meta: 12px;", "--ddf-type-meta: 12px; --ddf-type-tiny: 10px;", 1),
            "important in block": css.replace("--ddf-hit: 44px;", "--ddf-hit: 44px !important;", 1),
            "low contrast": css.replace("--ddf-muted: #52635C;", "--ddf-muted: #9AA5A1;", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, css, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check(body), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
