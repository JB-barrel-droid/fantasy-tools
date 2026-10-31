## 2026-10-31 - Draft expiry review corrections / JEG-1452

Contract: address Claude's five findings on draft PR #1254 in the existing Codex branch, with one push and no merge. Keep dry-run enabled.

### Verified (check named)
- `python3 -m unittest scripts.stale_draft_expiry tests.test_stale_draft_expiry`: 16 tests pass, including mocked gh/Linear/time orchestration, both dry-run gates, two-PR rechecks, fresh exemptions, label normalization, duplicate suppression, and re-warning after closure/reopen activity.
- `git diff --check`: passed.
- Workflow inspection: PR access is read-only, issues write permission removed, checkout credential persistence disabled. Live activation requires a separate permission change.
- `make validate`: stopped in sync at the missing Playwright Chromium headless-shell executable; later gate stages did not run. Generated files were restored or moved outside the checkout.

### Claimed, not confirmed
- Live selection and current CI are pending GitHub access; the previous live dry-run exhausted the Mac's REST quota. No live PR comments or closures were performed during this correction.
- Independent delta review is pending on the new head. PR remains a draft; no merge or deploy.
