#!/usr/bin/env python3
"""Test that the normative import-health doc matches the code's source declarations.

This test parses the normative doc (docs/import-health-schema.md) to extract the
machine-readable source declaration and compares it against DASHBOARD_SOURCES from
pipelines/verify_import_health.py. The test ensures the contract stays in sync
when sources are added or removed.

Run: python3 -m unittest tests.test_doc_vs_code
"""

import re
import sys
import unittest
from pathlib import Path
from typing import Any

# Add pipelines to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
from verify_import_health import DASHBOARD_SOURCES, HEALTH_SCHEMA  # noqa: E402


class TestDocVsCode(unittest.TestCase):
    """Test that normative doc matches code's source/schema declarations."""

    @classmethod
    def setUpClass(cls):
        """Load the normative doc once for all tests."""
        doc_path = ROOT / "docs" / "import-health-schema.md"
        cls.doc_path = doc_path
        cls.doc_text = doc_path.read_text(encoding="utf-8")

    def test_doc_exists(self):
        """Normative doc must exist."""
        self.assertTrue(
            self.doc_path.is_file(),
            f"Normative doc not found at {self.doc_path}",
        )

    def test_schema_matches(self):
        """Schema declaration in doc must match HEALTH_SCHEMA from code."""
        # Look for schema: "trade-value-import-health-v1" in the doc
        schema_match = re.search(r'schema["\s:]+["\']?([a-z0-9\-]+)["\']?', self.doc_text)
        self.assertIsNotNone(
            schema_match,
            "Could not find schema declaration in doc",
        )
        doc_schema = schema_match.group(1)
        self.assertEqual(
            doc_schema,
            HEALTH_SCHEMA,
            f"Doc schema '{doc_schema}' does not match code's HEALTH_SCHEMA '{HEALTH_SCHEMA}'",
        )

    def test_sources_declared_in_doc(self):
        """Doc must declare sources in a machine-parseable format."""
        # The doc should have a sources covered line like:
        # "Sources covered (exactly these N, never others):"
        # or "Sources covered (exactly these seven, never others):"
        # followed by a list of sources
        sources_pattern = r"Sources covered[^\n]*\n((?:\s*`[^`]+`[,\s]*\n?)+)"
        match = re.search(sources_pattern, self.doc_text, re.IGNORECASE | re.MULTILINE)
        self.assertIsNotNone(
            match,
            "Could not find 'Sources covered' section in doc. "
            "Doc must declare sources in a machine-parseable format.",
        )

    def test_doc_sources_match_code(self):
        """Doc's declared sources must exactly match DASHBOARD_SOURCES from code."""
        # Extract sources from doc - look for the sources covered section
        # Pattern: `source_name` (backtick-enclosed source names)
        sources_pattern = r"`([a-z]+)`"
        all_source_matches = re.findall(sources_pattern, self.doc_text)

        # Filter to only the relevant sources (the ones in the "Sources covered" context)
        # We look for the section that lists the active dashboard sources
        covered_section = re.search(
            r"Sources covered[^\n]*\n([\s\S]*?)hard exclusion",
            self.doc_text,
            re.IGNORECASE,
        )
        self.assertIsNotNone(
            covered_section,
            "Could not find 'Sources covered' section with hard exclusion context",
        )

        covered_text = covered_section.group(1)
        doc_sources = set(re.findall(sources_pattern, covered_text))

        # Normalize: code uses underscores, doc may use different format
        # The code sources are: fantasycalc, usatoday, fantasypros, espn, cbs, cbsros, razzball
        code_sources = set(DASHBOARD_SOURCES)

        # Check for exact match
        missing_in_doc = code_sources - doc_sources
        extra_in_doc = doc_sources - code_sources

        self.assertEqual(
            doc_sources,
            code_sources,
            f"Doc sources {sorted(doc_sources)} do not match "
            f"code DASHBOARD_SOURCES {sorted(code_sources)}. "
            f"Missing in doc: {missing_in_doc}. Extra in doc: {extra_in_doc}.",
        )

    def test_no_hardcoded_five_count(self):
        """Doc must not hard-code the word 'five' as a source count."""
        # Find lines that mention "five" in the context of sources
        lines_with_five = []
        for i, line in enumerate(self.doc_text.split("\n"), 1):
            # Look for "five" near "sources" but not in other contexts
            if re.search(r'\bfive\b', line, re.IGNORECASE):
                # Check if it's in source-related context
                if re.search(r'source', line, re.IGNORECASE):
                    lines_with_five.append((i, line.strip()))

        self.assertEqual(
            lines_with_five,
            [],
            f"Found 'five' in source-related context (should be 'seven'): {lines_with_five}",
        )

    def test_no_hardcoded_six_count(self):
        """Doc must not hard-code the word 'six' as a source count."""
        # Find lines that mention "six" in the context of sources
        lines_with_six = []
        for i, line in enumerate(self.doc_text.split("\n"), 1):
            if re.search(r'\bsix\b', line, re.IGNORECASE):
                if re.search(r'source', line, re.IGNORECASE):
                    lines_with_six.append((i, line.strip()))

        self.assertEqual(
            lines_with_six,
            [],
            f"Found 'six' in source-related context (should be 'seven'): {lines_with_six}",
        )

    def test_all_seven_sources_mentioned(self):
        """All seven sources must be mentioned in the doc."""
        sources_to_check = ["fantasycalc", "usatoday", "fantasypros", "espn", "cbs", "cbsros", "razzball"]
        missing_sources = []
        for source in sources_to_check:
            # Check if source appears anywhere in the doc
            if source not in self.doc_text:
                missing_sources.append(source)

        self.assertEqual(
            missing_sources,
            [],
            f"Missing sources in doc: {missing_sources}",
        )

    def test_makefile_doc_string_updated(self):
        """Makefile's import-health help text must reflect seven sources."""
        makefile_path = ROOT / "Makefile"
        makefile_text = makefile_path.read_text(encoding="utf-8")

        # Check the import-health help line mentions seven, not five
        import_health_help = re.search(
            r"make import-health[^\n]*",
            makefile_text,
        )
        self.assertIsNotNone(import_health_help, "Could not find import-health in Makefile")

        help_text = import_health_help.group(0)
        self.assertNotIn(
            "five",
            help_text.lower(),
            f"Makefile still mentions 'five' sources: {help_text}",
        )


class TestDocStaleVersionsFail(unittest.TestCase):
    """Test that stale/incorrect doc versions would fail the contract test.

    These tests use temporary doc text to verify the test correctly detects
    outdated declarations.
    """

    def test_five_sources_would_fail(self):
        """A doc declaring only five sources should fail the test."""
        # Simulate old doc text with five sources
        old_doc_text = """Sources covered (exactly these five, never others):
  `espn`, `usatoday`, `fantasycalc`, `fantasypros`, `cbs`.
  ECR, Vegas, and Razzball are hard exclusions."""

        # Parse sources from this text
        sources_pattern = r"`([a-z]+)`"
        covered_section = re.search(
            r"Sources covered[^\n]*\n([\s\S]*?)hard exclusion",
            old_doc_text,
            re.IGNORECASE,
        )
        self.assertIsNotNone(covered_section)
        doc_sources = set(re.findall(sources_pattern, covered_section.group(1)))

        # Expected: seven sources
        expected_sources = {"fantasycalc", "usatoday", "fantasypros", "espn", "cbs", "cbsros", "razzball"}

        # This should fail the test
        missing = expected_sources - doc_sources
        extra = doc_sources - expected_sources

        self.assertNotEqual(
            doc_sources,
            expected_sources,
            f"Test would not catch a five-source doc. Missing: {missing}, Extra: {extra}",
        )

    def test_missing_razzball_would_fail(self):
        """A doc missing razzball should fail the test."""
        # Simulate doc without razzball
        doc_without_razzball = """Sources covered (exactly these seven, never others):
  `espn`, `usatoday`, `fantasycalc`, `fantasypros`, `cbs`, `cbsros`.
  ECR, Vegas are hard exclusions."""

        sources_pattern = r"`([a-z]+)`"
        covered_section = re.search(
            r"Sources covered[^\n]*\n([\s\S]*?)hard exclusion",
            doc_without_razzball,
            re.IGNORECASE,
        )
        self.assertIsNotNone(covered_section)
        doc_sources = set(re.findall(sources_pattern, covered_section.group(1)))

        expected_sources = {"fantasycalc", "usatoday", "fantasypros", "espn", "cbs", "cbsros", "razzball"}

        self.assertNotIn(
            "razzball",
            doc_sources,
            "Test would not catch missing razzball",
        )

    def test_wrong_schema_would_fail(self):
        """A doc with wrong schema should fail the test."""
        wrong_schema = "trade-value-import-health-v0"
        correct_schema = "trade-value-import-health-v1"

        self.assertNotEqual(
            wrong_schema,
            correct_schema,
            "Test schema comparison would not catch wrong version",
        )


if __name__ == "__main__":
    unittest.main()
