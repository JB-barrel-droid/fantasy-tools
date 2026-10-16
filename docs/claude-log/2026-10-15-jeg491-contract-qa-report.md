## 2026-10-15 - JEG-491 contract QA report tool

Contract: a QA report that runs every automatable feature-contract line, writes per-ID pass/fail plus the pending ("to build") gaps to docs/qa-report.md, and exits non-zero on any failing line. Reuses the checks from JEG-506/602 (tests/test_v2_contract_render.py); nothing in them changed.

### Verified (check named)
- `python scripts/contract_qa_report.py` ran the real browser checks: 46 of 49 live lines pass, 14 pending, exit 1.
- `tests.test_contract_qa_report` (4 tests: failing line and page errors give FAIL, pending ticket status shown, summaries drop the "to build" text). Added to `make test-core`; `make qa-report` runs the tool.
- The report found three live failures on current main, so it does what it is for: GL-05 (freshness fixture: usatoday/cbs show "Not updating" instead of prior/unknown, no source Current), GL-09 and GL-16 (the `ddf_value_charts` series is not offered in Compare's series list and Rank by cannot switch to it). Not fixed here; those are front-end/engine lanes' files. Needs an owner.

### Claimed, not confirmed
- Whether GL-05/09/16 are real regressions or date drift in the freshness fixture (today is 2026-10-15/16): not investigated.
- Ticket status for pending lines comes from `--status JEG-x=State` (default "unknown"); not wired to Linear.
- Not built, by decision: the Google Drive contracts.md/contract-check.js and a live-site mode (the repo mirror replaces them; the checks patch the page with fixtures).
