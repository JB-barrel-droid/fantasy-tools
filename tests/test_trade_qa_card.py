"""Tests for the trade-QA card builder and the dashboard's fetch-with-fallback wiring.

Two contracts under test:

1. Positive: ``pipelines/build_trade_qa_card.py`` emits a valid JSON file at
   ``dist/modules/trade-qa-card.json`` carrying exactly the four keys the
   dashboard reads (``round``, ``date``, ``errors``, ``frameworks``). A missing or
   malformed payload means future QA rounds cannot land without re-editing
   ``modules/dashboard.html``.

2. Negative (fallback): when ``dist/modules/trade-qa-card.json`` is missing
   or unparseable, the dashboard MUST still render. The wiring is an
   ``(async () => { ... try { fetch(...) } catch { /* fallback */ } })``
   IIFE in modules/dashboard.html. We verify the contract by code inspection
   because the JS does not have a headless harness wired up here, and
   document the fallback path explicitly so a future regression that
   removes the catch would surface as a fail.

The negative case has no headless JS harness in this repo, so we verify by
inspection: the block must contain a ``try {`` that calls ``fetch`` and a
matching ``catch`` that swallows errors so qaData stays at qaDataLiteral.
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

DASHBOARD = REPO / "modules" / "dashboard.html"
OUTPUT_JSON = REPO / "dist" / "modules" / "trade-qa-card.json"
BUILDER = REPO / "pipelines" / "build_trade_qa_card.py"

# Region of dashboard.html the brief restricts us to. Edits outside it are
# out of scope.
DASHBOARD_FENCE = (1455, 1700)


def _run_builder() -> subprocess.CompletedProcess:
    """Invoke the builder; assertions on the result live in the tests."""
    return subprocess.run(
        [sys.executable, str(BUILDER)],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )


class BuilderEmitsValidJsonTest(unittest.TestCase):
    def test_builder_runs_clean(self):
        result = _run_builder()
        self.assertEqual(
            result.returncode, 0,
            f"Builder exited {result.returncode}.\nstdout: {result.stdout}\nstderr: {result.stderr}",
        )
        self.assertIn("Wrote", result.stdout)

    def test_emitted_file_is_valid_json(self):
        self.assertTrue(OUTPUT_JSON.exists(), f"{OUTPUT_JSON} not produced")
        # Must not raise -- proves the file is syntactically valid JSON.
        payload = json.loads(OUTPUT_JSON.read_text())
        self.assertIsInstance(payload, dict)

    def test_emitted_file_has_all_four_keys(self):
        payload = json.loads(OUTPUT_JSON.read_text())
        # Brief lists exactly these four keys; anything else is drift.
        self.assertEqual(
            sorted(payload.keys()),
            ["date", "errors", "frameworks", "round"],
            f"Trade-QA card shape changed. Got keys: {sorted(payload.keys())}",
        )

    def test_round_and_date_match_round1_bake(self):
        """Round 1 was 2026-09-30; future rounds replace this test with a
        round-N reference. Locking the literal here proves the builder
        baked what is in the HTML today (not invented values).
        """
        payload = json.loads(OUTPUT_JSON.read_text())
        self.assertEqual(payload["round"], 1)
        self.assertEqual(payload["date"], "2026-09-30")

    def test_errors_and_frameworks_are_nonempty_arrays(self):
        payload = json.loads(OUTPUT_JSON.read_text())
        self.assertIsInstance(payload["errors"], list)
        self.assertIsInstance(payload["frameworks"], list)
        self.assertGreaterEqual(len(payload["errors"]), 1)
        self.assertGreaterEqual(len(payload["frameworks"]), 1)
        # Each entry must be an object with a string id, otherwise the
        # dashboard template (`${e.id}`, `${f.id}`) renders "undefined".
        for e in payload["errors"]:
            self.assertIsInstance(e, dict)
            self.assertIsInstance(e.get("id"), str)
        for f in payload["frameworks"]:
            self.assertIsInstance(f, dict)
            self.assertIsInstance(f.get("id"), str)


class DashboardFallbackContractTest(unittest.TestCase):
    """When the JSON is missing or unparseable, the dashboard MUST still
    render. We verify this by inspection because the JS does not have a
    headless harness wired up in this repo (and adding one is out of scope
    for JEG-309). The test fails if any of the fallback guarantees is
    broken, surfacing regressions that would silently blank the card.
    """

    def setUp(self):
        self.text = DASHBOARD.read_text()
        self.lines = self.text.splitlines()

    def _slice_fence(self):
        start, end = DASHBOARD_FENCE
        return "\n".join(self.lines[start - 1:end])

    def test_fallback_block_lives_in_allowed_region(self):
        """The brief restricts edits to lines 1455-1700. The fallback IIFE
        and the literal it falls back to must both live there -- a fix
        outside the fence would conflict with other workers.
        """
        fence = self._slice_fence()
        self.assertIn("qaDataLiteral", fence)
        self.assertIn("trade-qa-card.json", fence)
        # The literal closing `};` is also inside the fence.
        self.assertRegex(fence, r"\};")

    def test_dashboard_fetches_trade_qa_card_json(self):
        fence = self._slice_fence()
        # The fetch URL must be exactly the file the builder emits. A
        # relative path keeps it portable across the live site's base URL.
        self.assertRegex(fence, r'fetch\(\s*"trade-qa-card.json"')

    def test_dashboard_swallows_fetch_errors(self):
        """A 404 or network error must NOT bubble out and blank the card.
        The wiring is an IIFE with try { fetch ... } catch { fallback }.

        We verify each piece independently rather than trying to regex-match
        the whole nested block: the IIFE body contains many `{`/`}` inside
        string templates and object literals, which makes a single greedy
        match fragile.
        """
        fence = self._slice_fence()
        # 1. The IIFE opener and closer present in the allowed region.
        self.assertRegex(fence, r"\(async\s*\(\)\s*=>\s*\{")
        self.assertRegex(fence, r"\}\)\(\);")
        # 2. qaDataLiteral referenced (the fallback constant).
        self.assertIn("qaDataLiteral", fence)
        # 3. A try block that contains the fetch.
        try_idx = fence.find("try {")
        self.assertNotEqual(try_idx, -1, "try { not found inside IIFE region")
        # 4. A catch that follows the try.
        self.assertRegex(fence, r"\}?\s*catch\s*\(")
        # 5. The catch body must NOT re-throw -- otherwise a 404 blanks
        # the card. The body sits between `catch (e) {` and the next
        # unmatched closing brace; we inspect the slice that follows.
        catch_m = re.search(
            r"catch\s*\([^)]*\)\s*\{(?P<body>.*?)(?:\n\s{2,4}\})",
            fence,
            re.DOTALL,
        )
        self.assertIsNotNone(catch_m, "catch block not found in IIFE")
        catch_body = catch_m.group("body")
        self.assertNotIn(
            "throw", catch_body,
            "QA-card fetch catch block re-throws; the dashboard would "
            "blank on a 404. Remove the throw.",
        )

    def test_qa_data_falls_back_to_literal_when_fetch_fails(self):
        """When the fetch rejects (404, network, parse), qaData must still
        resolve to qaDataLiteral so the summary, errors, and frameworks all
        render. We check the contract: an `await resp.json()` that throws
        must NOT leave qaData undefined.
        """
        fence = self._slice_fence()
        # The IIFE must initialise qaData from qaDataLiteral BEFORE the try,
        # so any throw inside the try leaves the fallback in place.
        self.assertRegex(fence, r"let\s+qaData\s*=\s*qaDataLiteral\s*;")
        # And the only assignments to qaData must come from the success path.
        # Anything that assigns before the try would clobber the fallback.
        before_try = fence.split("try", 1)[0]
        self.assertNotRegex(
            before_try,
            r"\bqaData\s*=\s*(?!qaDataLiteral)",
            "qaData is reassigned before the try block; a fetch failure "
            "would lose the qaDataLiteral fallback.",
        )

    def test_summary_uses_qa_data_round_and_date(self):
        """Brief: summary uses JSON's round/date, not hardcoded. The summary
        template reads ${qaData.round} and ${qaData.date}; with the fetch
        wiring in place, qaData is the JSON values, so this is automatic.
        Guard it explicitly so a future edit cannot regress to hardcoded
        "QA Round 1 · 2026-09-30" inline.
        """
        fence = self._slice_fence()
        self.assertIn("QA Round ${qaData.round}", fence)
        self.assertIn("${qaData.date}", fence)
        # Belt-and-braces: there must be no hardcoded literal round/date
        # pair inside the summary template.
        self.assertNotIn(
            'QA Round 1 · "2026-09-30"',
            fence,
            "Summary template hardcodes round/date; should read from qaData.",
        )


if __name__ == "__main__":
    unittest.main()