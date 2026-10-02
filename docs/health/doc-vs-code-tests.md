# Doc-vs-Code Contract Tests

This document explains how the doc-vs-code tests work and how to extend them for future normative contracts.

## Overview

The `tests/test_doc_vs_code.py` module verifies that the normative documentation (`docs/import-health-schema.md`) stays in sync with the code's actual behavior (`pipelines/verify_import_health.py`). This prevents downstream consumers from silently using stale or incorrect source declarations.

## What Gets Tested

### Source Declaration Contract

The test parses the normative doc to extract the machine-readable source declaration and compares it against `DASHBOARD_SOURCES` from the code:

```python
from verify_import_health import DASHBOARD_SOURCES
```

The test verifies:
1. **Exact match**: Doc sources must equal code sources (no more, no less)
2. **Schema match**: The doc's schema declaration must equal `HEALTH_SCHEMA`
3. **No hardcoded counts**: The doc must not say "five" or "six" in source context
4. **All sources mentioned**: Each of the seven sources must appear in the doc
5. **Makefile updated**: The help text must reflect the correct count

### Failure Detection

The test correctly catches:
- **Missing sources**: Omitting `cbsros` or `razzball`
- **Wrong count**: Stating "five" instead of "seven"
- **Schema drift**: Using `v0` instead of `v1`
- **Makefile staleness**: Help text still saying "five"

## Current Sources

As of 2026-10-02, the seven active dashboard trade-value sources are:
- `fantasycalc`
- `usatoday`
- `fantasypros`
- `espn`
- `cbs`
- `cbsros`
- `razzball`

## How to Extend for New Sources

### Adding a New Source

When adding a new source to the health checker:

1. **Update the code** (`pipelines/verify_import_health.py`):
   - Add the source to `DB_SOURCES` tuple
   - Add configuration to `SOURCE_CONFIGS` dict
   - If needed, add to `WEEK_DESIGNATED_SOURCES`

2. **Update the normative doc** (`docs/import-health-schema.md`):
   - Update "Sources covered" line to say "exactly these N"
   - Add the new source to the backtick-enclosed list
   - Update any prose references to source count
   - Add per-source table notes if applicable

3. **Update the Makefile**:
   - Update the `make import-health` help text

4. **Run the test**:
   ```bash
   python3 -m unittest tests.test_doc_vs_code
   ```

The test will fail if the doc and code are out of sync, ensuring the contract is maintained.

### Adding a New Contract Test

To add a new normative contract test (e.g., for a different schema or configuration):

1. Create a new test class in `tests/test_doc_vs_code.py`
2. Follow the pattern:
   - Parse the normative doc using regex
   - Import the corresponding value from code
   - Assert exact match
   - Add negative tests to verify stale versions fail

Example pattern:
```python
class TestNewContract(unittest.TestCase):
    def test_doc_matches_code(self):
        doc_value = extract_from_doc()
        code_value = import_from_code()
        self.assertEqual(doc_value, code_value)
```

## Why This Matters

Without doc-vs-code tests:
- A source can be removed from the code but documentation still lists it
- The doc can say "five sources" while the code checks seven
- Downstream consumers may use stale contracts and miss active sources

The test ensures the contract is **normative** — what the doc says is actually what the code does.

## Running the Tests

```bash
# Run just the doc-vs-code tests
python3 -m unittest tests.test_doc_vs_code

# Run all unit tests (includes doc-vs-code)
make test-unit
```

## Test Isolation

These tests are **hermetic** — they:
- Read the doc and code from the filesystem
- Use no external services (no Supabase, no network)
- Can run in CI where data/raw is absent
- Use temporary doc text for negative tests (stale version detection)
