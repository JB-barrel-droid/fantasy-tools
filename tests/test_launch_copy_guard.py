"""JEG-1130: launch copy follows the approved PMM doc (Jeremy, 2026-10-26, amended by JEG-1126).

"At launch we don't require any integrations with platforms or creation of user accounts.
Everything is designed for the user to quickly copy-paste info in and save it."

  * no user-visible string in app/v2 says we support, connect to, sync with or work with
    Sleeper, ESPN or Yahoo (platform names appear only in "how to copy" tips);
  * storage copy says "on this device", never "in this browser";
  * the page descriptions and social tags (v2 head and the classic page) name no publisher:
    marketing copy says "the market" (positioning guardrail, legal / Phase 2).
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

V2 = ROOT / "app" / "v2"
CLASSIC = ROOT / "app" / "trade-value-chart" / "index.html"

PLATFORM = re.compile(r"\b(Sleeper|ESPN|Yahoo)\b")
CLAIM = re.compile(r"\b(works? with|supports?|connect(s|ed)? (to|with)|syncs?( with)?|integrat\w*)\b", re.I)
BROWSER_STORAGE = re.compile(r"(stays|saved|kept|stored) in (this|your) browser", re.I)
PUBLISHERS = re.compile(r"FantasyCalc|USA Today|FantasyPros|\bCBS\b|\bESPN\b|Razzball|KeepTradeCut|\bKTC\b", re.I)
STRING = re.compile(r'"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`|\'(?:[^\'\\\n]|\\.)*\'')
META = re.compile(r'<meta\s+(?:name|property)="(description|og:title|og:description)"\s+content="([^"]*)"')


def user_strings(path: Path) -> list[tuple[int, str]]:
    """String literals (JS) or text lines (HTML), with code comments dropped."""
    out = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        code = line.strip()
        if code.startswith(("//", "*", "/*", "<!--")):
            continue
        if path.suffix == ".js":
            out.extend((n, m.group(0)) for m in STRING.finditer(line))
        else:
            out.append((n, re.sub(r"<[^>]+>", " ", line)))
    return out


def violations(path: Path) -> list[str]:
    found = []
    for n, text in user_strings(path):
        if PLATFORM.search(text) and CLAIM.search(text):
            found.append(f"{path.name}:{n} claims a platform connection: {text.strip()[:140]}")
        if BROWSER_STORAGE.search(text):
            found.append(f"{path.name}:{n} says 'in this browser' (say 'on this device'): {text.strip()[:140]}")
    return found


class LaunchCopyGuard(unittest.TestCase):
    def test_no_platform_claims_or_browser_storage_copy_in_v2(self):
        files = sorted(V2.glob("*.js")) + [V2 / "shell.html"]
        found = [v for f in files for v in violations(f)]
        self.assertEqual([], found, "\n".join(found))

    def test_guard_catches_a_platform_claim(self):
        tmp = ROOT / "build" / "jeg1130_guard_probe.js"
        tmp.parent.mkdir(exist_ok=True)
        try:
            tmp.write_text('const a = "Works with Sleeper, ESPN and Yahoo.";\nconst b = "Pasted text stays in this browser.";\n'
                           '// Sleeper sync comment is fine\nconst c = "On ESPN, open League, then Rosters.";\n', encoding="utf-8")
            self.assertEqual(2, len(violations(tmp)))
        finally:
            tmp.unlink(missing_ok=True)

    def test_v2_head_copy_names_no_publisher(self):
        for name in ("DESCRIPTION", "OG_DESCRIPTION", "OG_TITLE"):
            self.assertIsNone(PUBLISHERS.search(getattr(build_v2_page, name)), name)

    def test_classic_page_meta_names_no_publisher(self):
        metas = META.findall(CLASSIC.read_text(encoding="utf-8"))
        self.assertEqual({"description", "og:title", "og:description"}, {k for k, _ in metas})
        for key, content in metas:
            self.assertIsNone(PUBLISHERS.search(content), f"{key}: {content}")


if __name__ == "__main__":
    unittest.main()
