"""JEG-1372: the legacy local (stdio) MCP server is retired. It described a
0-70 scale and an 85% starter weight that contradict the site and the hosted
connector. The hosted connector (`supabase/functions/mcp/`) is the one MCP
server; maintained docs and the AI-assistant surfaces point there only.
Dated logs (`docs/claude-log/`, `docs/research/`) and `archive/` are history
and may still name the old folder."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOSTED = "functions/v1/mcp"
MAINTAINED = [
    "HANDOFF.md",
    "docs/README.md",
    "docs/values-endpoint.md",
    "docs/use-ddf-in-claude-chatgpt.md",
    "app/llm/llms.txt",
]


class LocalMcpRetiredTests(unittest.TestCase):
    def test_local_server_folder_is_gone(self):
        self.assertFalse((ROOT / "mcp-server").exists(), "mcp-server/ (the stdio server) should be removed")

    def test_maintained_docs_do_not_point_at_the_local_server(self):
        for rel in MAINTAINED:
            with self.subTest(doc=rel):
                text = (ROOT / rel).read_text()
                for phrase in ("mcp-server/", "stdio", "local mcp server"):
                    self.assertFalse(phrase in text.lower(), f"{rel} still mentions {phrase!r}")

    def test_setup_surfaces_still_name_the_hosted_connector(self):
        self.assertIn("{{MCP_URL}}", (ROOT / "app/llm/llms.txt").read_text())
        self.assertIn(HOSTED, (ROOT / "docs/use-ddf-in-claude-chatgpt.md").read_text())
        self.assertTrue((ROOT / "supabase/functions/mcp/index.ts").exists())


if __name__ == "__main__":
    unittest.main()
