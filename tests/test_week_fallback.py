"""JEG-1156 / JEG-1157 (Jeremy, 2026-10-27, option A): when no trade chart has posted the content
week, DDF Value falls back to the latest published week, labeled. Node checks with a pinned day:
- weeks.ts (get-values) and product-data.js (the page) agree on the values week, label and drops;
- the get-values handler itself on the flip day, a normal day, and with no chart at all;
- the MCP tools carry the week label;
- the Python reference (pipelines/value_reference.py) follows the same rule.
The rendered page check is tests/test_week_fallback_render.py.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ["node", "--experimental-strip-types", "--no-warnings"]


def run_node(script, *args):
    return subprocess.run([*NODE, str(ROOT / "tests" / "node" / script), *args],
                          capture_output=True, text=True, timeout=300, cwd=str(ROOT))


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WeekFallbackTests(unittest.TestCase):
    def test_edge_and_page_rules_agree(self):
        out = run_node("week_fallback_check.mjs")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_mcp_tools_name_the_week(self):
        out = run_node("mcp_week_check.mjs")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_get_values_handler_on_pinned_days(self):
        from tests import _render_env
        _render_env.ensure_built()
        out = run_node("get_values_week_check.mjs", str(ROOT / "dist"))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


class ReferenceWeekFallbackTests(unittest.TestCase):
    def test_reference_keeps_latest_week_on_the_flip(self):
        import copy
        import sys
        from datetime import timedelta
        sys.path.insert(0, str(ROOT / "pipelines"))
        import value_reference as ref
        from nfl_week import content_week_start
        inp = ref.Inputs.load()
        charts = [k for k in ref.PUBLISHED if inp.section(k) is not None]
        weeks = [ref.section_week(inp.section(k), inp.today)[0] for k in charts]
        week = max(w for w in weeks if w is not None)
        # The charts' own week: nothing behind. The flip day: the reference week stays the charts' week.
        for day in (content_week_start(week) + timedelta(days=3), content_week_start(week + 1)):
            inp.today = day
            fresh = ref.freshness(inp)
            self.assertEqual(fresh["reference_week"], week)
            behind = sorted(k for k in charts if fresh["series"][k]["behind_values_week"])
            expected = sorted(k for k, w in zip(charts, weeks) if w is not None and w < week)
            self.assertEqual(behind, expected, day)
        # A chart a week further behind is still left out on the flip day.
        inp.today = content_week_start(week + 1)
        inp.fixture = copy.deepcopy(inp.fixture)
        inp.section(charts[0])["week_designated"] = f"Week {week - 1}"
        self.assertTrue(ref.freshness(inp)["series"][charts[0]]["behind_values_week"])


if __name__ == "__main__":
    unittest.main()
