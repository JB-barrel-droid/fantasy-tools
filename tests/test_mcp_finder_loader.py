"""JEG-1129 review: the PR branch had reverted three pieces of main's MCP edge function.

- index.ts must load finder.js through evalFinder (JEG-1037, #903): finder.js throws after publishing
  TradeValueFinder when there is no DOM, so a bare eval leaves find_trades unavailable.
- index.ts must keep the values cache bounded (CACHE_MAX): league-keyed entries otherwise grow without limit.
- tools.ts methodology must say DDF Value is the average of the four published trade charts (JEG-1073, #919),
  not the older "projections and charts are blended" text.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MCP = ROOT / "supabase/functions/mcp"


class McpFinderLoaderTest(unittest.TestCase):
    def test_index_loads_finder_through_eval_finder(self):
        src = (MCP / "index.ts").read_text()
        self.assertIn('import { evalFinder, type Finder } from "./find-trades.ts";', src)
        self.assertIn("finder = evalFinder(await res.text(), evalFn);", src)
        self.assertNotIn("(globalThis as any).TradeValueFinder", src)

    def test_values_cache_is_bounded(self):
        src = (MCP / "index.ts").read_text()
        self.assertIn("const CACHE_MAX = ", src)
        self.assertIn("if (cache.size >= CACHE_MAX) cache.delete(", src)

    def test_methodology_names_ddf_value_as_chart_average(self):
        src = (MCP / "tools.ts").read_text()
        self.assertIn("The headline value (DDF Value) is the average of the four published trade charts", src)
        self.assertNotIn("Several projection sources and published trade charts are blended", src)


if __name__ == "__main__":
    unittest.main()
