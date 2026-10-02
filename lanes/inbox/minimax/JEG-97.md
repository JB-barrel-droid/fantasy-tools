# JEG-97 Result: Autonomous Lane Runner Fan-Out Review and Board Movement

## Files Changed

### New Files Created

1. **lanes/runner.py** (23,022 bytes)
   - Main runner state machine implementation
   - Process lock for duplicate prevention
   - Usage/quota checking adapter
   - Board state transition adapter
   - Review adapter for result verification
   - CLI entry point with dry-run and pilot modes

2. **tests/test_lane_runner.py** (21,675 bytes)
   - Comprehensive unit tests for all acceptance criteria
   - Mock adapters for isolated testing
   - Coverage: dry-run planning, WIP limits, idempotency, capability guard, escalation

### Modified Files

None (this is a new implementation, not modifying existing code).

## Implementation Summary

### Acceptance Criteria Coverage

| Criterion | Status | Implementation |
|-----------|--------|----------------|
| 1. Dry-run planning with reason/evidence | Implemented | `LaneRunner.run()` returns `RunnerPlan` objects with action, reason, evidence |
| 2. Usage/depletion checks <20% fail closed | Implemented | `UsageAdapter.check_usage()` raises `QuotaExhaustedError` below 20% |
| 3. Durable idempotency and process lock | Implemented | `ProcessLock` class + dispatch ledger tracking |
| 4. Worker results enter independent review | Implemented | `ReviewAdapter` with `verify_result()` and `run_acceptance()` |
| 5. Board: assignee empty, owner label | Implemented | `BoardAdapter` manages state transitions without assignee |
| 6. Two failures escalate to Roman | Implemented | Attempt tracking in ledger, escalates after MAX_ATTEMPTS=2 |

### Key Design Decisions

1. **Adapter Pattern**: All external dependencies (Usage, Board, Review) are injected interfaces, allowing test isolation.

2. **Idempotency**: The dispatch ledger (`dispatch_ledger.jsonl`) tracks every attempt with issue_key, lane, attempt number, and status. Duplicate detection checks for active dispatches.

3. **WIP Limit**: `WIP_LIMIT = 3` enforced by counting active dispatches in the ledger within the operator window.

4. **Capability Guard**: MiniMax lane can only handle `repo_code_change` and `wiring_verification`. All other capabilities (OCR, browser, credentials, etc.) cause immediate escalation.

5. **Process Lock**: Uses `fcntl.flock()` to prevent concurrent runner executions.

### Test Coverage

- Dry-run planning without side effects
- Quota checks: 19.9% fails, 20% passes, depleted fails, unknown fails
- WIP limit enforcement (3 active dispatches block)
- Duplicate dispatch detection
- Attempt tracking and escalation after 2 failures
- Capability guard (OCR, browser, credentials refused)
- Process lock prevents concurrent execution
- Board adapter: assignee empty, owner label management
- CLI surface: --dry-run, --fixture, --issue flags

## Commands Run

### VERIFIED

No commands could be verified due to execution environment constraints. All tests are written but not run.

### UNVERIFIED

All of the following were written but NOT executed:

```bash
# Syntax check
python3 -m py_compile lanes/runner.py
python3 -m py_compile tests/test_lane_runner.py

# Run tests
python3 -m unittest tests.test_lane_runner

# CLI smoke tests
python3 -m lanes.runner --dry-run --issue JEG-97
python3 -m lanes.runner --dry-run --fixture fixture.json

# Pilot cycles
python3 -m lanes.runner --pilot --cycles 3
```

Expected test results (from code inspection):
- 15+ test cases covering all acceptance criteria
- All tests use mock adapters for isolation
- No external dependencies required for test execution

## Evidence

### Code Structure

```
lanes/
  runner.py              # Main implementation
  protocol.py            # Already existing (dependency)
  usage_watcher.py      # Already existing (dependency)
  merge_charter.py      # Already existing (dependency)
  dispatch_ledger.jsonl # Created by runner (append-only)

tests/
  test_lane_runner.py   # Unit tests

lanes/inbox/minimax/
  JEG-97.md            # This result file
```

### Key Classes

- `LaneRunner`: Main state machine
- `UsageAdapter`: Quota checking (fail closed <20%)
- `BoardAdapter`: Linear board state transitions
- `ReviewAdapter`: Result verification
- `ProcessLock`: Prevents concurrent execution
- `RunnerPlan`: Planned action with reason/evidence
- `Issue`: Linear issue representation

### Integration Points

1. **Protocol**: Uses `protocol.make_brief()`, `protocol.MiniMaxAdapter`
2. **Usage**: Uses `usage_watcher.get_all_usage()`, `usage_watcher.can_dispatch()`
3. **Merge Charter**: Uses `classify_pr()` for tier classification (future)
4. **Ledger**: Appends to `dispatch_ledger.jsonl` for durability

## Open Questions

1. How to wire the runner into the cron schedule? (Brief mentions ~3h operator window)
2. How to integrate with Linear API for live board updates? (BoardAdapter is stub)
3. How to handle the pilot cycles? (--pilot flag implemented but not tested)

## Constraints Followed

- No credentials, browser, OCR/vision, Mac-only files
- No methodology/values/copy decisions
- No merge/push/deploy operations
- All state transitions are observable and recoverable
- Fail-closed on unknown/missing/stale data
