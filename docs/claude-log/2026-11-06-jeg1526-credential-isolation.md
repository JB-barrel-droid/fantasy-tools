## 2026-11-06 - JEG-1526 credential isolation fix

Contract: fix the independent review's credential-copy blocker; leave work
uncommitted as instructed. Replace tree copying with selected tracked,
nonignored files and explicit private-path and symlink checks.

### Verified (check named)
- `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_week_transition_readiness.py -q -s -p no:cacheprovider`:
  11 passed, 3 subtests passed. New synthetic-credential regression failed
  before the implementation fix and passed afterwards.
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_week_transition_readiness -v`:
  11 tests, OK. Existing fail-closed assertions retained.
- `git diff --check`: passed.

### Claimed, not confirmed
- Real Docker diagnostics and full rehearsal were not executed. Existing
  missing DB integrations remain BLOCKED; no READY result is claimed.
- No production access, publication, or commit performed.
