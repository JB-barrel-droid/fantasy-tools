## 2026-11-03 - JEG-1217 / JEG-1255 pause-control main integration

Contract: integrate exact main `1e87a3cacbbe645c8a8b85d3cccd4f65e679d1fe` after the parent-approved release-window switch. Preserve the control/timing exactly, obtain fresh exact-head CI under the every-main-movement rule, and leave merge/release and subsequent switch-off with the parent.

### Verified (check named)

- The user authorized the existing 90-minute pause switch, with standing permission to stop/start publishing as needed. Exactly one on/90 workflow dispatch was submitted. Run 41677199363 completed successfully; current main's only delta from ba010ff6 is `.github/main-write-pause.json`, committed as 1e87a3ca at 16:44:34 UTC.
- Actual control: paused=true, started `2026-11-03T16:44:33Z`, expires `2026-11-03T18:14:33Z` (exactly 90 minutes), scope fidelity-pulse / health-artifacts / rebuild-chain / source-vintage-check. The file and its reason/timing are copied byte-for-byte from main, not rewritten or extended here.
- Normal `git merge --no-commit --no-ff 1e87a3ca` into prior ticket head `d9d038763b26588c756c27f5fd94ac6d347d6adf` has no conflicts. Staged tree equals the automatic merge: `9155ca6d6a0c971cc62bc588f40340dc51eca65f`. This log is the sole manual addition.
- Smallest meaningful control checks: staged path set is exactly the control file; JSON matches main; existing main_write_guard.decision reports the pause active for all four scoped writers and inactive for all six named daily/weekly snapshot writers; at expiry+1 second the valid pause no longer applies. These are read-only validator calls, not a schedule change or future automation.
- `git diff --cached --quiet HEAD -- app pipelines tests .github/workflows Makefile`: feature implementation, completed-search manager pricing, assertions, commands and strict finalizers are unchanged. `git diff --cached --check` passes. No redundant broad local validation was repeated.
- Current-main Deploy dashboard run is 41677294571; its actual status is checked separately, with no green inferred from dispatch or pause success. Earlier 868384fd checks completed success; d9d03876 checks remain prior-head evidence only after this new main movement.

### Claimed, not confirmed

- Fresh exact-head CI must reach terminal and actual main must be rechecked before readiness reporting. Historical feature tests/reviews are reused, not substituted for the new head's gate.
- Parent owns explicit switch-off and verification that a publisher resumes. Automatic expiry is a failsafe, not evidence that restoration has already been verified. No off dispatch or control timing change is performed here.
- No PR merge, new dispatch beyond the single explicitly approved on/90 action, manual cancellation, force/main push, deletion, Supabase/access/schedule change, rank-guard implementation, assertion weakening, or denied optional publication retry.
