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


# JEG-1137: the Fieldnotes layer (docs/design/jeg-1209-fieldnotes/recommendation.md "Shared visual and interaction
# system", approved via JEG-1209) is opt-in under <html data-design="fieldnotes">. These checks pin its role values in
# light and both dark forms, its WCAG contrast, that every Fieldnotes rule is scoped to the flag, and that the default
# (unflagged) values of every token it overrides are exactly today's.
FN_MARK = "/* JEG-1137: Fieldnotes foundation (opt-in)."
FLAG = '[data-design="fieldnotes"]'
DEFAULT_ONLY = f":root:not({FLAG}) "
DARK_MEDIA = "@media (prefers-color-scheme: dark)"
FONT_DIR = CSS.parent / "fonts"
FIELDNOTES = {
    "light": {"canvas": "#F5F2EA", "surface": "#FFFDF8", "subtle": "#EAE8DF", "ink": "#182D27", "muted": "#52635C",
              "line": "#D4D8CD", "control": "#79897F", "action": "#126044", "action-ink": "#FFFFFF",
              "positive": "#245D46", "negative": "#922F3E", "warning": "#80500F", "focus": "#175BC1"},
    "dark": {"canvas": "#101B17", "surface": "#192720", "subtle": "#26372D", "ink": "#EEF3E8", "muted": "#B5C4B8",
             "line": "#3D4E43", "control": "#7F9688", "action": "#A6DFBE", "action-ink": "#11271C",
             "positive": "#A6DFBE", "negative": "#FFB4BE", "warning": "#EBC486", "focus": "#A9C7FF"},
}
# Which existing (and new) token names carry each Fieldnotes role.
ROLE_TOKENS = {
    "canvas": ["--v2-canvas", "--ddf-canvas"], "surface": ["--v2-surface", "--ddf-surface"],
    "subtle": ["--ddf-subtle", "--ddf-neutral-tint"], "ink": ["--v2-ink", "--ddf-ink", "--ddf-neutral-ink"],
    "muted": ["--v2-muted", "--ddf-muted"], "line": ["--v2-border", "--ddf-line"],
    "control": ["--v2-field-border", "--ddf-control"],
    "action": ["--v2-action", "--v2-action-text", "--v2-action-strong", "--ddf-action"],
    "action-ink": ["--v2-action-ink", "--ddf-action-ink"], "positive": ["--ddf-good-ink"],
    "negative": ["--v2-negative", "--ddf-bad-ink"], "warning": ["--v2-older", "--ddf-warn-ink"],
    "focus": ["--v2-focus", "--ddf-focus"],
}
FN_INVARIANT = {"--ddf-type-hero": "52px", "--ddf-type-body": "16px", "--ddf-type-support": "14px", "--ddf-type-meta": "12px",
                "--ddf-line-body": "1.5", "--ddf-space-mid": "12px", "--ddf-space-7": "64px",
                "--ddf-page-pad-phone": "16px", "--ddf-page-pad-desktop": "32px", "--ddf-content-max": "1184px",
                "--ddf-radius-card": "16px", "--ddf-hit": "44px", "--ddf-motion-feedback": "160ms",
                "--ddf-font-headline": "var(--ddf-font-display)"}
# Text >= 4.5:1; control edges and the focus ring >= 3:1 (WCAG 1.4.3 / 1.4.11).
FN_TEXT_PAIRS = [(fg, bg) for fg in ("--v2-ink", "--v2-muted", "--v2-negative", "--ddf-bad-ink", "--v2-action-text",
                                     "--ddf-good-ink", "--ddf-warn-ink") for bg in ("--v2-canvas", "--v2-surface")] + [
    ("--v2-action-ink", "--v2-action"), ("--ddf-action-ink", "--ddf-action"), ("--ddf-action-ink", "--ddf-action-hover"),
    ("--ddf-surface", "--ddf-ink"),   # pressed segment
    ("--v2-canvas", "--v2-negative"),  # failed-state symbol and the error toast
]
FN_EDGE_PAIRS = [(fg, bg) for fg in ("--v2-field-border", "--ddf-control", "--v2-focus") for bg in ("--v2-canvas", "--v2-surface")]
# Default (unflagged) values of every token the Fieldnotes layer overrides, as they were before JEG-1137.
DEFAULTS = {
    "light": {
        "--v2-canvas": "#F3F7F7", "--v2-surface": "#FFFFFF", "--v2-ink": "#142B25", "--v2-muted": "#64736F",
        "--v2-border": "#DEE5E2", "--v2-field-border": "#80908B", "--v2-action": "#087F5B", "--v2-action-ink": "#FFFFFF",
        "--v2-action-text": "#087F5B", "--v2-action-strong": "#066B4C", "--v2-negative": "#B33F50", "--v2-older": "#A56320",
        "--v2-focus": "#087F5B",
        "--ddf-canvas": "var(--v2-canvas)", "--ddf-surface": "var(--v2-surface)", "--ddf-line": "var(--v2-border)",
        "--ddf-ink": "#1A2824", "--ddf-muted": "#52635C", "--ddf-action": "#0C7A56", "--ddf-action-ink": "#FFFFFF",
        "--ddf-good-ink": "#085C40", "--ddf-bad-ink": "#8C2434", "--ddf-warn-ink": "#7A4510",
        "--ddf-neutral-tint": "#ECEFEE", "--ddf-neutral-ink": "#1A2824",
        "--ddf-font-ui": 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif', "--ddf-font-headline": "var(--ddf-font-ui)",
        "--ddf-type-body": "14px", "--ddf-type-meta": "12px", "--ddf-page-pad-phone": "16px",
        "--ddf-radius-card": "12px", "--ddf-hit": "44px",
    },
    "dark": {
        "--v2-canvas": "#0E1714", "--v2-surface": "#15211D", "--v2-ink": "#E4EEEA", "--v2-muted": "#93A39E",
        "--v2-border": "#2A3833", "--v2-field-border": "#62756F", "--v2-action": "#2FA57B", "--v2-action-ink": "#06140F",
        "--v2-action-text": "#38B386", "--v2-action-strong": "#5CCB9F", "--v2-negative": "#E07A8A", "--v2-older": "#D9944E",
        "--ddf-ink": "#E8F2ED", "--ddf-muted": "#9DB0A8", "--ddf-action": "#6EE4B8", "--ddf-action-ink": "#062018",
        "--ddf-good-ink": "#8FE0BE", "--ddf-bad-ink": "#F2A3AE", "--ddf-warn-ink": "#F0BE82",
        "--ddf-neutral-tint": "#232E29", "--ddf-neutral-ink": "#E8F2ED",
    },
}


def rules(css: str) -> list[tuple[tuple[str, ...], str]]:
    """Every block as (enclosing preludes, outermost first; its own text). Comments are dropped."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out, stack, buf = [], [], ""
    for ch in css:
        if ch == "{":
            stack.append(" ".join(buf.split()))
            buf = ""
        elif ch == "}":
            if stack:
                out.append((tuple(stack), buf))
                stack.pop()
            buf = ""
        else:
            buf += ch
    return out


def split_fieldnotes(css: str) -> tuple[str, str]:
    at = css.index(FN_MARK)
    return css[:at], css[at:]


def mode_tokens(css: str, flagged: bool) -> dict[str, dict[str, str]]:
    """Custom properties set on the root in light, dark (media query) and dark (data-theme), flagged or not."""
    modes: dict[str, dict[str, str]] = {"light": {}, "dark-media": {}, "dark-attr": {}}
    for ctx, body in rules(css):
        selector, media = ctx[-1], ctx[:-1]
        if (FLAG in selector) != flagged:
            continue
        base = selector.replace(FLAG, "")
        if not media and base == ":root":
            mode = "light"
        elif media == (DARK_MEDIA,) and base == ':root:not([data-theme="light"])':
            mode = "dark-media"
        elif not media and base == ':root[data-theme="dark"]':
            mode = "dark-attr"
        else:
            continue
        modes[mode].update(dict(re.findall(r"(--[a-z0-9-]+):\s*([^;]+?)\s*;", body)))
    return modes


def fieldnotes_names(css: str) -> set[str]:
    return {name for values in mode_tokens(css, flagged=True).values() for name in values}


def check_fieldnotes(css: str) -> list[str]:
    errors = []
    default_css, fn_css = split_fieldnotes(css)
    fn = mode_tokens(css, flagged=True)
    if "!important" in fn_css:
        errors.append("the Fieldnotes layer uses !important")
    # 1. Every Fieldnotes rule is scoped to the flag (the @font-face only declares a face; nothing unflagged names it).
    for ctx, _ in rules(fn_css):
        selector = ctx[-1]
        if selector.startswith("@font-face") or selector.startswith("@media"):
            continue
        unscoped = [part.strip() for part in selector.split(",") if FLAG not in part]
        if unscoped:
            errors.append(f"Fieldnotes rule not scoped to {FLAG}: {unscoped}")
    # Outside the block the flag may only be excluded (JEG-1281): a default-site rule whose every selector starts with
    # :root:not(<flag>) and a descendant, and that sets no custom property, never styles the flagged page and leaves the
    # pinned default tokens alone. Any other rule naming the flag belongs in the block.
    for ctx, body in rules(default_css):
        if not any(FLAG in c for c in ctx):
            continue
        parts = [part.strip() for part in ctx[-1].split(",")]
        excluded = FLAG not in " ".join(ctx[:-1]) and all(
            part.startswith(DEFAULT_ONLY) and FLAG not in part[len(DEFAULT_ONLY):] for part in parts)
        if not excluded or re.search(r"--[\w-]+\s*:", body):
            errors.append(f"a data-design rule sits outside the Fieldnotes block: {ctx[-1]}")
    for ctx, body in rules(default_css):
        if "Fraunces" in body or "--ddf-font-display" in body:
            errors.append(f"an unflagged rule uses the display face: {ctx[-1]}")
    # 2. Role values, light and both dark forms.
    for role, names in ROLE_TOKENS.items():
        for name in names:
            for mode, want in (("light", FIELDNOTES["light"][role]), ("dark-media", FIELDNOTES["dark"][role]),
                               ("dark-attr", FIELDNOTES["dark"][role])):
                got = fn[mode].get(name, "")
                if got.upper() != want:
                    errors.append(f"Fieldnotes {mode} {name} is {got!r}, want {want} ({role})")
    if fn["dark-media"] != fn["dark-attr"]:
        errors.append("Fieldnotes dark media-query values differ from the data-theme=dark values")
    colors = {k for k, v in fn["light"].items() if v.startswith("#")}
    if colors - set(fn["dark-attr"]):
        errors.append(f"Fieldnotes light colors with no dark value (light would leak into dark): {sorted(colors - set(fn['dark-attr']))}")
    for name, want in FN_INVARIANT.items():
        if fn["light"].get(name) != want:
            errors.append(f"Fieldnotes {name} is {fn['light'].get(name)!r}, want {want}")
    if not re.search(r'--ddf-font-display:\s*"Fraunces"', fn_css):
        errors.append("--ddf-font-display does not lead with Fraunces")
    if not re.search(r"@media \(max-width: 600px\) \{ :root\[data-design=\"fieldnotes\"\] \{ --ddf-type-hero: 37px; \} \}", fn_css):
        errors.append("phone hero is not 37px")
    if not re.search(r"@media \(prefers-reduced-motion: reduce\) \{ :root\[data-design=\"fieldnotes\"\] \{ --ddf-motion-feedback: 0ms; \} \}", fn_css):
        errors.append("reduced motion does not settle instantly")
    # 3. Contrast in both themes.
    for mode in ("light", "dark-attr"):
        values = {**fn["light"], **fn[mode]}
        for pairs, floor in ((FN_TEXT_PAIRS, 4.5), (FN_EDGE_PAIRS, 3.0)):
            for fg, bg in pairs:
                f, b = values.get(fg, ""), values.get(bg, "")
                if not (f.startswith("#") and b.startswith("#")):
                    errors.append(f"Fieldnotes {mode}: {fg}/{bg} are not literal colors ({f!r}, {b!r})")
                elif contrast(f, b) < floor:
                    errors.append(f"Fieldnotes {mode}: {fg} on {bg} is {contrast(f, b):.2f}:1, below {floor}")
    # 4. Default (unflagged) values of every overridden token are unchanged.
    default = mode_tokens(css, flagged=False)
    overridden = fieldnotes_names(css)
    for mode, want_mode, effective in (
            ("light", "light", default["light"]),
            ("dark-media", "dark", {**default["light"], **default["dark-media"]}),
            ("dark-attr", "dark", {**default["light"], **default["dark-attr"]})):
        want = {**DEFAULTS["light"], **DEFAULTS[want_mode]}
        for name in sorted(overridden):
            if name in want and effective.get(name) != want[name]:
                errors.append(f"default {mode} {name} changed: {effective.get(name)!r}, was {want[name]!r}")
    return errors


class FieldnotesTokenTests(unittest.TestCase):
    def test_fieldnotes_layer(self):
        self.assertEqual(check_fieldnotes(CSS.read_text(encoding="utf-8")), [])

    def test_default_tokens_unchanged(self):
        css = CSS.read_text(encoding="utf-8")
        default = mode_tokens(css, flagged=False)
        for mode, effective in (("light", default["light"]),
                                ("dark", {**default["light"], **default["dark-media"]}),
                                ("dark", {**default["light"], **default["dark-attr"]})):
            want = {**DEFAULTS["light"], **DEFAULTS[mode]}
            self.assertEqual({k: effective.get(k) for k in want}, want)
        # Every name the layer overrides has a pinned default, or is new under the flag.
        new = {"--ddf-subtle", "--ddf-control", "--ddf-focus", "--ddf-action-hover", "--ddf-font-display",
               "--ddf-type-hero", "--ddf-type-support", "--ddf-line-body", "--ddf-space-mid", "--ddf-space-7",
               "--ddf-page-pad-desktop", "--ddf-content-max", "--ddf-radius-control", "--ddf-motion-feedback", "--ddf-ease"}
        overridden = fieldnotes_names(css)
        self.assertEqual(sorted(overridden - new - set(DEFAULTS["light"])), [])
        self.assertEqual(sorted(new & set(default["light"])), [], "a 'new' Fieldnotes name already exists unflagged")

    def test_font_is_self_hosted_with_license(self):
        css = CSS.read_text(encoding="utf-8")
        face = re.search(r"@font-face \{[^}]*font-family: \"Fraunces\";[^}]*\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
        self.assertIsNotNone(face, "no Fraunces @font-face")
        self.assertIn('url("fonts/fraunces.woff2") format("woff2")', face.group(0))
        self.assertIn("font-weight: 600;", face.group(0))
        self.assertNotIn("http", face.group(0), "the face must be self-hosted")
        self.assertEqual((FONT_DIR / "fraunces.woff2").read_bytes()[:4], b"wOF2")
        self.assertIn("SIL Open Font License", (FONT_DIR / "FONT-LICENSE.txt").read_text(encoding="utf-8"))

    def test_fieldnotes_checks_fail_on_broken_css(self):
        css = CSS.read_text(encoding="utf-8")
        _, fn_css = split_fieldnotes(css)
        broken = {
            "dark role dropped": css.replace("--ddf-bad-ink: #FFB4BE; ", "", 1),
            "unscoped rule": css.replace(':root[data-design="fieldnotes"] .ddf-fn-btn--primary {', ".ddf-fn-btn--primary {", 1),
            "low contrast": css.replace("--v2-muted: #52635C;", "--v2-muted: #9AA5A1;", 1),
            "default edited": css.replace("--v2-canvas: #F3F7F7;", "--v2-canvas: #F5F2EA;", 1),
            "flag rule in default block": css.replace("body.v2 { margin: 0;", ':root[data-design="fieldnotes"] body.v2 { margin: 0;', 1),
            "flag excluded on the root": css.replace("body.v2 { margin: 0;", ':root:not([data-design="fieldnotes"]) { --v2-border: #000000; }\nbody.v2 { margin: 0;', 1),
            "token set in a flag-excluded rule": css.replace("body.v2 { margin: 0;", ':root:not([data-design="fieldnotes"]) .v2-app { --v2-border: #000000; }\nbody.v2 { margin: 0;', 1),
            "flag excluded then named": css.replace("body.v2 { margin: 0;", ':root:not([data-design="fieldnotes"]) [data-design="fieldnotes"] body.v2 { margin: 0;', 1),
            "hero not 37 on phone": css.replace("--ddf-type-hero: 37px;", "--ddf-type-hero: 52px;", 1),
            "important in layer": css.replace("--ddf-space-7: 64px;", "--ddf-space-7: 64px !important;", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, css, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(check_fieldnotes(body), [], f"checks did not catch: {name}")
        self.assertIn("--v2-muted: #52635C;", fn_css, "the low-contrast mutation must hit the Fieldnotes block")


if __name__ == "__main__":
    unittest.main()
