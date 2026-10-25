## 2026-10-23 - Session-log policy (JEG-975 follow-up)

Contract: Jeremy decided "1 - A" on 2026-10-23 (JEG-975): every session that changes anything writes a docs/claude-log entry. PR #871 merged before its last commit, so the three edits are re-applied here. Branch `be/JEG-975-session-log` from origin/main 2c43c1cf.

### Verified (check named)
- `git grep "Every session that changes anything" origin/main` found nothing, and CLAUDE.md on main still had "No separate session log is required", so the edits were missing.
- `python3 -m unittest tests.test_doc_staleness`: 4 tests OK (run on the earlier commit with identical text). A grep of tests/ found no test pinning the old sentence.

### Claimed, not confirmed
- No other docs test was run; none reads this CLAUDE.md sentence.
