# JEG-19: K/DST Coverage Implementation Brief

## Status: Draft - Awaiting Review

## Files Changed

### New Files Created

1. **`tests/test_kdst_coverage_contract.py`** - Unit tests for K/DST coverage contract
   - 6 test classes covering:
     - KdstSnapshotValidationTest: unknown/stale snapshot detection
     - KdstNoPeerComparisonTest: verifies no ECR/Razzball/PM data for K/DST
     - KdstZeroVsMissingTest: distinguishes zero-valued from missing
     - KdstDatasetStatusTest: appropriate status in dataset_status panel
     - KdstToggleDefaultOffTest: UI toggle defaults to off
     - KdstScoringInvariantTest: K/DST values identical across scorings

## Commands Run + Outputs

### VERIFIED (Actually Executed)

- **File creation**: Successfully created `tests/test_kdst_coverage_contract.py`
  - File size: 12,644 bytes
  - Location: `/home/hatch/workspace/worktrees/wt-jeg19/tests/test_kdst_coverage_contract.py`

- **Read existing audit**: Verified `docs/kdst-source-audit.md` exists and contains:
  - Source audit showing ESPN-only for K/DST (45 K, 32 DST)
  - No peer sources (USA Today, FantasyCalc, FantasyPros, CBS, Razzball all have 0 K/DST)
  - Recommendation for option 1 (honest exclusion) or option 2 (ESPN-only separate scale)

- **Read current fixture**: Verified `data/fixtures/current/players.json` shows:
  - `kdst_snapshot`: "?" (unknown)
  - `n_k`: 45, `n_dst`: 32
  - K/DST rows have `pricing: "espn_only"`
  - K/DST rows have `ecr_ros: None`

- **Read existing inputs**: Verified K/DST input files exist:
  - `data/inputs/espn_k_ppg_2026-09-21.json` (45 kickers)
  - `data/inputs/espn_dst_ros_2026-09-21.json` (32 defenses)
  - Both have `as_of: "2026-09-21"` (11 days old as of 2026-10-02)

- **Read frontend toggle**: Verified `app/trade-value-chart/index.html` contains:
  - Line 1674: `<input type="checkbox" id="includeSpecialists"> Include K/DST`
  - Default is unchecked (off)

### UNVERIFIED (Written but Not Run)

- **Python compile check**: `python3 -m py_compile tests/test_kdst_coverage_contract.py`
  - BLOCKED: Permission system issue in current session
  - Syntax manually verified by reading file back

- **Unit test execution**: `python3 -m unittest tests.test_kdst_coverage_contract`
  - NOT RUN: Per brief instructions - tests are proposed, not executed in sandbox

## Implementation Summary

### What Was Implemented

Per the brief requirements:

1. **Test file created** (`tests/test_kdst_coverage_contract.py`)
   - Tests for unknown K/DST snapshot ("?" in metadata)
   - Tests for stale K/DST detection
   - Tests verifying K/DST have no peer sources (ecr_ros = None, no rz/pm data)
   - Tests distinguishing zero-valued K/DST from missing
   - Tests verifying pricing label enforcement ("espn_only")
   - Tests for scoring-invariant values
   - Tests for toggle default-off state

2. **Documentation preserved**: Re-used existing audit (`docs/kdst-source-audit.md`)

### What Remains (Requires Approval)

Per acceptance criteria:

1. **Brief review**: Reviewer confirms hold remains; no build dispatch until Jeremy unpauses

2. **Fresh source verification**: Operator verifies new source evidence and fresh ESPN K/DST input before values become live

3. **Approved explanation option**: If explanation-only is approved, show visible reason for unavailable K/DST

4. **Separate leg option**: If separate leg is approved, implement with own scale/guards/coverage

5. **Production verification**: Operator renders toggle, comparison view, widget after implementation

### Key Findings from Audit

- **Only ESPN provides K/DST**: 45 kickers, 32 DST in current fixture
- **No peers**: ECR, Razzball, Prediction Markets, USA Today, FantasyCalc all have 0 K/DST
- **Stale data**: Current input files dated 2026-09-21 (11 days old)
- **Unknown content vintage**: `kdst_snapshot = "?"` - we don't know when ESPN actually published
- **Scoring-invariant**: K/DST values identical across standard/half/full PPR

### Constraints Respected

Per brief:
- No credentials, browser, OCR/vision, Mac-only files
- No methodology/value/copy decisions (reserved for Jeremy/Roman)
- No test suite execution (Roman runs tests outside sandbox)
- No merges/pushes/deploys
- Work only in `~/workspace/worktrees/wt-jeg19`

## Branch Information

- **Branch**: `minimax/jeg19-brief`
- **Base**: `origin/main` (bebfeb3)
- **Worktree**: `/home/hatch/workspace/worktrees/wt-jeg19`
