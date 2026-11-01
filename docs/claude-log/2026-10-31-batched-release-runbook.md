## 2026-10-31 - Batched release runbook / JEG-1445

Contract: carry JEG-1444 decision 13 into both successor merge duties and keep the cutover policy aligned with the portable rules PR. No release execution.

### Verified (check named)
- Source inspection: PSpice and Muse share the batch cadence/cap, per-head gates, conflict deferral, isolated releases and approval requirements; Muse retains API identity and marked comments.
- git diff --check, paired-duty and cutover-policy equality checks passed across both documentation branches.
- Linear comment marker inspection: new decision-13 milestone marker absent from the comments read.

### Claimed, not confirmed
- No batch, dry run, merge or deploy performed. make validate unavailable without headless Chromium; GitHub CI must run the gate before review.
