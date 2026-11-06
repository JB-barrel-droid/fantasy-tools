## 2026-11-06 - Complete the post-rebuild scenario sandbox for the breach renderer / JEG-1523

Written by Muse.

Contract: unblock PR #1323's security-contracts failure without weakening
any assertion. The failing test —
tests.test_rebuild_chain_workflow.RebuildChainWorkflowTest
.test_post_rebuild_validation_blocks_the_push — fails identically on
current main (verified on the untouched main tree at 8a9d4597): it is not
caused by this branch.

Root cause: JEG-1529's breach rendering gave
pipelines/record_post_rebuild_validation.py a sibling dependency,
`from validation_breach import records_from_log, render`. The scenario
sandbox in tests/test_rebuild_chain_workflow.py runs the REAL recorder
from an isolated copy and already copies its other real dependency
(pipelines/candidate_evidence.py, added when validate gained that
wrapper) — but not pipelines/validation_breach.py. The copied recorder
died with ModuleNotFoundError before it could mark the chain status, so
the status stayed green and the test reported "the chain status was not
published as failed after a red validate".

Fix: the sandbox now also copies pipelines/validation_breach.py, exactly
mirroring the candidate_evidence.py precedent in the same function. No
assertion, expectation, or production file changes.

### Verified (check named)

- On the untouched main tree (8a9d4597) with only this patch applied:
  `python3 -m unittest tests.test_rebuild_chain_workflow` — OK (the full
  module, including the mutation tests that prove dropped/swallowed/
  unrecorded validation is still caught).
- The same single test run against the unpatched main tree fails with
  the CI message, confirming the diagnosis.

### Claimed, not confirmed

- CI on the new PR #1323 head after this commit is pushed; the delta
  re-review of this commit is a coordinator step after the push.
