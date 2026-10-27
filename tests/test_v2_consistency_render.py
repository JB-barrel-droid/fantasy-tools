"""v2 dashboard consistency: one minus sign, one agreement phrase, no jargon or in-app arrows (JEG-977).

Loads the built page headless and reads what a reader sees on Compare a trade (the example trade), the Values
auditing tabs, Trade targets and Player values. It requires:
  * one minus sign: no ASCII hyphen used as a minus before a digit (U+2212 is the minus), and no "+0.0" / "-0.0"
    zero (zero is "0.0");
  * one agreement phrase: "N of M charts agree", never "trade charts agree";
  * no reader-visible W7-style week codes, bare "FA", "arbitrage", or "N of M players" vanity counts;
  * in-app links (href "v2/#..." or "#...") carry no external-link arrow; links that open another site keep it;
  * Trade targets: the Market consensus difference carries the Gap's sign (market minus ours), never the opposite;
  * the finder's "no trade found" sentence is grammatical for one chart (checked on the source string).
Discrimination: test_guard_fails_on_broken_builds serves a v2.js / audit file with each fix undone and requires the
checks to fail on each.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_deal_read_render import _served, V2_JS, ROOT

APP = ROOT / "app" / "v2"
AUDIT_PIE_JS = APP / "audit-pie.js"
FINDER_JS = APP / "finder.js"
TRADE_JS = APP / "trade.js"

HASHES = ("#compare-trade", "#values-auditing", "#values-auditing/single-source", "#trade-targets", "#player-values", "#writing/how-values")
READ = """() => ({
  text: document.body.innerText,
  links: [...document.querySelectorAll('a[href]')].filter(a => a.getClientRects().length)
    .map(a => ({href: a.getAttribute('href'), text: a.textContent.trim(), blank: a.target === '_blank'})),
  diffs: [...document.querySelectorAll('#v2TargetsPanel .t-diff, .v2-ttable .t-diff')].map(d => d.textContent.trim()),
})"""

HYPHEN_MINUS = re.compile(r"(^|[\s(\[])-\d")
BANNED = {
    "'trade charts agree' (the phrase is 'N of M charts agree')": re.compile(r"trade charts agree"),
    "W7-style week code": re.compile(r"\bW\d{1,2}\b"),
    "bare FA": re.compile(r"\bFA\b"),
    "arbitrage": re.compile(r"arbitrage", re.I),
    "N of M players count": re.compile(r"\b\d[\d,]* of \d[\d,]* players\b"),
    "signed zero": re.compile(r"(^|[\s(])[+−-]0\.0(?!\d)"),
}


def reader_problems(tag: str, snap: dict) -> list[str]:
    out = []
    text = snap["text"]
    if HYPHEN_MINUS.search(text.replace("\n", " ")) or any(HYPHEN_MINUS.search(line) for line in text.split("\n")):
        sample = next(line for line in text.split("\n") if HYPHEN_MINUS.search(line))
        out.append(f"[{tag}] hyphen used as a minus sign: {sample.strip()[:100]!r}")
    for name, rx in BANNED.items():
        m = rx.search(text)
        if m:
            line = next(l for l in text.split("\n") if rx.search(l))
            out.append(f"[{tag}] {name}: {line.strip()[:100]!r}")
    for link in snap["links"]:
        in_app = link["href"].startswith("#") or link["href"].startswith("v2/#")
        if in_app and "↗" in link["text"]:
            out.append(f"[{tag}] in-app link has the external-link arrow: {link['text']!r}")
    return out


def run_checks(patches=None) -> list[str]:
    """patches: {file name: (old, new)} served in place of the real v2 files, to prove the checks catch it."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    bodies = {}
    for name, (old, new) in (patches or {}).items():
        path = (ROOT / "dist" / "v2" / "index.html") if name == "index.html" else APP / name
        text = path.read_text(encoding="utf-8")
        assert old in text, f"patch anchor missing in {name}: {old!r}"
        bodies[name] = text.replace(old, new)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            for name, body in bodies.items():
                kind = "text/html" if name == "index.html" else "text/javascript"
                for pattern in ((f"**/v2/{name}*", "**/v2/") if name == "index.html" else (f"**/v2/{name}*",)):
                    page.route(pattern, lambda route, *_, body=body, kind=kind: route.fulfill(status=200, content_type=kind, body=body))
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            page.wait_for_timeout(500)
            saw_diff = False
            for hash_ in HASHES:
                page.evaluate("h => { location.hash = h; }", hash_)
                page.wait_for_timeout(1500)
                snap = page.evaluate(READ)
                errors += reader_problems(hash_, snap)
                if hash_ == "#trade-targets":
                    # JEG-1112 removed the Compare headline lines, so the chart count is read on the Trade targets rows.
                    if not re.search(r"\d+ of \d+ charts agree", snap["text"]):
                        errors.append("[#trade-targets] no 'N of M charts agree' on the target rows")
                    # The difference beside Market consensus is market minus ours, the Gap's own sign.
                    diffs = snap["diffs"]
                    saw_diff = saw_diff or bool(diffs)
                    for d in diffs:
                        if d != "0.0" and d[:1] not in ("+", "\u2212"):
                            errors.append(f"[targets] market difference {d!r} has no sign (it is market minus ours, like the Gap)")
                    # Wording must not give the opposite sign by word either.
                    if re.search(r"[▲▼]\s*\d+\.\d\s+(above|below)", snap["text"]):
                        errors.append("[targets] Market consensus still reads '▼ n below' (our value against the market), the opposite of the Gap sign")
            # One zero format, one minus: the Values auditing formatters, called directly.
            fmts = page.evaluate("() => { const A = window.AuditPie; return [A._fmtPct(0), A._fmtPct(-0.0004), A._fmtPct(-0.052), A._fmtPct(0.052), A._fmt(-0.01), A._fmt(-2.34)]; }")
            if fmts != ["0.0%", "0.0%", "\u22125.2%", "+5.2%", "0.0", "\u22122.3"]:
                errors.append(f"[values auditing] number formats {fmts}, want one zero ('0.0') and the U+2212 minus")
            if not saw_diff:
                errors.append("[targets] no Market consensus difference rows were rendered, so the sign convention was not checked")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


def source_problems(finder: str | None = None) -> list[str]:
    out = []
    finder = FINDER_JS.read_text(encoding="utf-8") if finder is None else finder
    if "available trade chart" in finder:
        out.append("finder.js: the 'no trade found' note still says 'available trade chart(s) say' (reads '1 of 1 available trade charts say')")
    trade = TRADE_JS.read_text(encoding="utf-8")
    if re.search(r"of \$\{\w+\} trade charts (agree|have)", trade):
        out.append("trade.js: a chart count still says 'trade charts'")
    return out


PATCHES = {
    "minus sign is a hyphen again (Values auditing)": {"audit-pie.js": ('.replace("-", "−");', ';')},
    "signed zero returns": {"audit-pie.js": ('(text === "0.0" ? "" : text.startsWith("-")', '(text.startsWith("-")')},
    "agreement phrase says 'trade charts'": {"v2.js": ("`${b.agree} of ${b.of} charts agree `", "`${b.agree} of ${b.of} trade charts agree `")},
    "week code W7 returns": {"v2.js": ("` · Week ${view.refWeek}`", "` · W${view.refWeek}`")},
    "arrow on an in-app link": {"index.html": ("See every value</a>", "See every value ↗</a>")},
    "market difference opposite to gap": {"v2.js": ("diff.textContent = fmtGap(-m.diff);", "diff.textContent = `${m.diff > 0 ? \"▲\" : \"▼\"} ${Math.abs(m.diff).toFixed(1)} ${m.diff > 0 ? \"above\" : \"below\"}`;")},
}


class ConsistencyRenderTest(unittest.TestCase):
    def test_reader_text_is_consistent(self):
        _render_env.ensure_built()
        self.assertEqual(run_checks(), [])
        self.assertEqual(source_problems(), [])

    def test_guard_fails_on_broken_builds(self):
        _render_env.ensure_built()
        for name, patches in PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(patches)
                except AssertionError as exc:
                    self.fail(f"patch no longer applies, update the simulated break: {exc}")
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")

    def test_source_guard_catches_old_finder_wording(self):
        original = FINDER_JS.read_text(encoding="utf-8")
        self.assertEqual(source_problems(original), [])
        broken = original.replace("the one available chart says", "available trade chart says")
        self.assertNotEqual(broken, original)
        self.assertNotEqual(source_problems(broken), [])


if __name__ == "__main__":
    unittest.main()
