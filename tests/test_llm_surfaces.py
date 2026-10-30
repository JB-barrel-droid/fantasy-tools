"""JEG-1028: the files an AI assistant needs to find and use the tools are built, filled in and consistent."""
import json
import re
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_llm_surfaces as b  # noqa: E402

MCP = "https://example.test/functions/v1/mcp"
SITE = "https://site.test/ddf/"
TOOLS = ["get_values", "get_player_value", "trade_targets", "compare_trade", "read_state", "make_state", "find_trades", "find_trades_league", "risers_fallers", "audit_values", "explain"]


class LlmSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dist = Path(cls.tmp.name)
        cls.written = b.build(cls.dist, SITE, MCP)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def read(self, rel):
        return (self.dist / rel).read_text(encoding="utf-8")

    def test_every_file_is_written_and_filled_in(self):
        for rel in ("llms.txt", "ddf-skill/SKILL.md", "mcp-server-card.json", ".well-known/mcp/server-card.json",
                    "get-values.openapi.yaml", "ddf-skill.zip"):
            self.assertTrue((self.dist / rel).is_file(), rel)
        for rel in ("llms.txt", "ddf-skill/SKILL.md", "mcp-server-card.json"):
            self.assertNotIn("{{", self.read(rel), rel)
        self.assertIn(MCP, self.read("llms.txt"))
        self.assertIn(SITE + "ddf-skill.zip", self.read("llms.txt"))

    def test_server_card_is_valid_and_lists_the_real_tools(self):
        card = json.loads(self.read("mcp-server-card.json"))
        self.assertEqual(card["transport"], {"type": "streamable-http", "url": MCP})
        self.assertEqual(card, json.loads(self.read(".well-known/mcp/server-card.json")))
        self.assertEqual(card["tools"], TOOLS)
        # The card must not drift from the function: every tool it lists is one the function serves.
        tools_ts = (ROOT / "supabase/functions/mcp/tools.ts").read_text()
        served = re.findall(r'^\s{4}name: "([a-z_]+)",', tools_ts, flags=re.M)
        self.assertEqual(sorted(served), sorted(TOOLS))

    def test_skill_zip_holds_the_skill_with_its_frontmatter(self):
        with zipfile.ZipFile(self.dist / "ddf-skill.zip") as zf:
            self.assertEqual(zf.namelist(), ["data-driven-football/SKILL.md"])
            text = zf.read("data-driven-football/SKILL.md").decode()
        self.assertEqual(text, self.read("ddf-skill/SKILL.md"))
        front = re.match(r"---\nname: ([a-z-]+)\ndescription: (.+)\n---\n", text)
        self.assertTrue(front, "SKILL.md needs name and description frontmatter")
        self.assertEqual(front.group(1), "data-driven-football")
        self.assertLessEqual(len(front.group(2)), 1024)

    def test_skill_and_llms_txt_teach_the_state_and_site_link_workflow(self):
        for rel in ("llms.txt", "ddf-skill/SKILL.md"):
            text = self.read(rel)
            for needle in ("read_state", "make_state", "Open this on the site", "ddf-state"):
                self.assertIn(needle, text, f"{rel} missing {needle}")
        # Every tool the skill tells the model to call exists.
        skill_tools = set(re.findall(r"`([a-z_]+)`", self.read("ddf-skill/SKILL.md"))) & set(TOOLS + ["compare_trade"])
        self.assertTrue(skill_tools <= set(TOOLS))

    def test_zip_is_reproducible(self):
        with tempfile.TemporaryDirectory() as other:
            b.build(Path(other), SITE, MCP)
            self.assertEqual((Path(other) / "ddf-skill.zip").read_bytes(), (self.dist / "ddf-skill.zip").read_bytes())

    def test_unfilled_placeholder_fails_the_build(self):
        with self.assertRaises(SystemExit):
            b.fill("see {{NOPE}}", SITE, MCP)

    def test_v2_head_points_assistants_to_llms_txt(self):
        import build_v2_page as v2
        html = v2.head_for_v2("<html><head><title>x</title></head><body></body></html>", at_root=True)
        self.assertIn(f'<link rel="alternate" type="text/plain" title="For AI assistants" href="{v2.SITE_URL}llms.txt">', html)


if __name__ == "__main__":
    unittest.main()
