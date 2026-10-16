# JEG-668: held-source reference mismatch fix

**Date:** 2026-10-16
**Ticket:** JEG-668
**Branch:** jeg-668-held-source-reference-fix

## Root cause

PR 530 (JEG-569 part 2) changed the JS engine so held sources stay in the
pipeline (weights, pie, universe) but are excluded from the DDF blend, Indexed
basis, and display. The Python reference (`pipelines/value_reference.py`) was
not updated: `Setting.state()` still dropped held sources from `eligible`
entirely, so they got no weights or pie share. This caused weight/pie/value
mismatches on every setting where a source is held.

## Changes

1. **`pipelines/value_reference.py`**: `Setting.state()` now adds held sources
   with data to `eligible` and a new `hidden` set. `bench_share_readout` accepts
   and filters hidden sources. `compute()` prior availability no longer requires
   inputs for the version (aligns with engine behavior).

2. **`tests/test_value_check.py`**: Updated `SeededMismatch` and
   `HeldAndUnpublishedInputs` tests to expect held sources in `composite_inputs`.
   `ReferenceMatchesEngine` tolerates zero-compared family-specific DDF versions
   when no sources of that family are included.

3. **`tests/test_asset_load_retry.py`**: `expected_inputs` now subtracts all
   excluded sources (not just held), fixing a pre-existing data-dependent failure.

4. **`Makefile`**: Wired `value-check-compare` into the `validate` target.

## Verified

- `value_check compare --rerun-engine --strict`: 0 mismatches, verdict=agree,
  715584 values compared
- `test_bench_share_readout_matches_reference`: 3/3 pass (was 16 failures)
- `test_spec_reference_value_pipeline`: 20/20 pass
- `test_value_reference_worked_example`: 16/16 pass
- `test_value_check`: 20/20 pass (was multiple failures)

## Pre-existing failures (not introduced by this PR)

- `test_ddf_composite_value`: 8 failures on unmodified main (data-dependent:
  no chart sources published for week 6)
