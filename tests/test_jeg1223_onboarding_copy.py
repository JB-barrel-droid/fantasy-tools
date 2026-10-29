"""JEG-1252: claim checks for the homepage AI onboarding copy pack (JEG-1223).

Reads the strings from the copy-pack tables in docs/product/jeg-1223-ai-onboarding-copy.md
and pins the acceptance checks that keep them truthful about the DDF connector: no
"same view" or round-trip promise, "free / no account / no sign-in" scoped to DDF,
troubleshooting that doesn't diagnose a disconnection, and Jeremy's headline pick.
Docs only: nothing here reads the built page.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / "docs" / "product" / "jeg-1223-ai-onboarding-copy.md"
CONNECT = "https://jb-barrel-droid.github.io/fantasy-tools/connect/"


def copy_pack(text: str) -> dict[str, dict[str, str]]:
    """ID -> {column header: cell} for every row of the tables under "## Copy pack"."""
    section = text.split("## Copy pack", 1)[1].split("\n## ", 1)[0]
    rows: dict[str, dict[str, str]] = {}
    header = None
    for line in section.splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if header is None:
            header = cells
            continue
        if set(line) <= set("|- "):
            continue
        rows[cells[0].strip("`")] = dict(zip(header, cells))
    return rows


# The 727b67b strings Codex's review flagged (JEG-1252). Each must trip at least one check.
FLAGGED = {
    "ai.body": "Give the chat your roster and the other team's, or your whole league's. Every answer links back here so you can keep working.",
    "ai.cta.note": "Connect the tool once: free, no account, no sign-in. You add one web address as a custom connector.",
    "ai.next.note": "Each answer says the date of the values and ends with a link to the same view here.",
    "ai.err.notconnected": "If the chat answers without Data Driven Football numbers or a site link, the tool isn't connected in that chat.",
    "ai.err.busy": "The tool is free and shared. If a chat says it's busy, wait a minute and ask again.",
}


def problems(key: str, s: str) -> list[str]:
    out = []
    if re.search(r"\b(tested|import\w*|sync\w*|automatic\w*|same numbers|guarantee\w*|will accept|perfect|sleeper|espn|yahoo)\b", s, re.I):
        out.append("banned claim word (check 3)")
    if re.search(r"same view|round trip|keep working|picks? up from there|exactly where", s, re.I):
        out.append("round-trip promise (check 8)")
    if re.search(r"\bfree\b|no (\w+ )?account|no (\w+ )?sign-in", s, re.I) and not re.search(r"Data Driven Football|DDF", s):
        out.append("free/no account not scoped to DDF (check 9)")
    if re.search(r"\b(isn't|is not|not) connected\b", s, re.I):
        out.append("diagnoses a disconnection (check 10)")
    return out


class OnboardingCopyClaims(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = copy_pack(DOC.read_text(encoding="utf-8"))
        cls.strings = {k: r["String"] for k, r in cls.rows.items()}

    def test_parsed_every_table(self):
        for key in ("ai.h", "ai.body", "ai.cta.note", "ai.next.note", "ai.link.more", "ai.err.notconnected", "ai.err.busy"):
            self.assertIn(key, self.strings)

    def test_headline_is_jeremys_pick(self):
        self.assertEqual(self.strings["ai.h"], "Find your best trade in Claude or ChatGPT")

    def test_connect_links_are_exact(self):
        self.assertEqual(self.rows["ai.cta"]["Destination"], f"`{CONNECT}`")
        self.assertIn(f"]({CONNECT})", self.strings["ai.err.notconnected"])

    def test_every_string_passes_the_claim_checks(self):
        # Acceptance checks 3, 8, 9 and 10.
        for key, s in self.strings.items():
            self.assertEqual(problems(key, s), [], f"{key}: {s}")

    def test_guard_flags_the_reviewed_strings(self):
        # The checks would have caught every string Codex flagged on 727b67b.
        for key, s in FLAGGED.items():
            self.assertTrue(problems(key, s), f"{key} not flagged: {s}")

    def test_league_wide_link_limit_is_said(self):
        note = self.strings["ai.next.note"].lower()
        self.assertIn("league-wide", note)
        self.assertIn("only your roster", note)

    def test_host_account_is_not_waived(self):
        # Check 9: the DDF-only "no account" must not read as "Claude or ChatGPT needs none".
        self.assertRegex(self.strings["ai.cta.note"], r"Claude or ChatGPT account")

    def test_troubleshooting_is_uncertain(self):
        # Check 10.
        self.assertIn("may not have used", self.strings["ai.err.notconnected"])


if __name__ == "__main__":
    unittest.main()
