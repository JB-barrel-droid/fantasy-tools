"""Regression: every firstOk() call site in the monitor dashboard must unwrap .json.

firstOk() in modules/dashboard.html returns {"path": p, "json": parsed} --
never the raw payload. On 2026-10-01 the Player Trace and Aggregate
Diagnostics sections assigned the wrapper directly and read .players /
.anomalies off it, so both sections rendered "not available" on production
even though player-trace.json and aggregate-diagnostics.json were served
correctly (HTTP 200, right sizes).

These tests fail against that broken state (traceData / data assigned the
wrapper with no .json dereference in the following statements) and pass
once each call site unwraps the result.
"""
import re
import unittest
from pathlib import Path

HTML = Path(__file__).resolve().parent.parent / "modules" / "dashboard.html"


def _call_sites(text):
    """Yield (var_name, offset) for simple `<var> = await firstOk(` assignments."""
    for m in re.finditer(r"(?P<var>[A-Za-z_$][\w$]*)\s*=\s*await\s+firstOk\(", text):
        yield m.group("var"), m.end()


class FirstOkUnwrapTest(unittest.TestCase):
    def test_every_firstok_call_site_unwraps_json(self):
        text = HTML.read_text()
        sites = list(_call_sites(text))
        self.assertTrue(sites, "no firstOk call sites found -- test wiring is stale")
        broken = []
        for var, end in sites:
            window = text[end : end + 2000]
            if not re.search(rf"\b{re.escape(var)}\.json\b", window):
                broken.append(var)
        self.assertFalse(
            broken,
            "firstOk() returns {path, json}; these call sites never dereference .json, "
            f"so they read fields off the wrapper: {broken}",
        )

    def test_promise_all_destructuring_still_unwraps(self):
        """The checkpoints/chain destructuring is the reference-correct pattern:
        both halves must be unwrapped with .json."""
        text = HTML.read_text()
        self.assertIn(
            "await Promise.all([firstOk(CP_PATHS), firstOk(CHAIN_PATHS)])", text
        )
        self.assertIn("cp.json", text)
        self.assertIn("ch.json", text)


if __name__ == "__main__":
    unittest.main()
