## 2026-10-16 - PR 659 (JEG-667 coverage triage)

- Added pipelines/coverage_triage.py, make coverage-triage, data/triage/coverage-accepted.json honored by review_comparison_candidate (names or floor, per content week; ignored when the source contradicts the drop).
- Verified: test_coverage_triage, test_coverage_acceptance, test_review_coverage_churn, test_review_candidate, test_promote_section pass; test_coverage_acceptance errors 8/8 on the old reviewer (negative proof).
- Claimed, not run: make validate (logic lanes in flux, skipped per Jeremy). Live runs: CBS from current status; FantasyCalc via REV=e37d751d (the Week-6 coverage hold, since superseded by a fidelity hold).
- No hold released; no decision recorded.
