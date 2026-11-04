## 2026-11-04 - Published history is authoritative for source freshness (JEG-1485)

Contract: a chain attempt's Week 9 labels must not resolve a source-lateness
alert while published history is missing. This reporting correction is one
bounded slice of the recurring rollover audit; it does not repair publication.

### Verified (check named)

- `ServedWeeksTest.test_candidate_status_is_not_a_publication_receipt` and
  `MainTest.test_failed_week_nine_candidate_cannot_resolve_alert_without_published_history`
  fail against the unchanged implementation at base `ee68dcc2` (two tests,
  eleven failing subcases). Missing/empty history was filled from candidate
  labels, and the CLI returned 0 instead of an incomplete-report error.
- The CLI regression supplies fresh probes and a failed Week 9 candidate,
  freezes Wednesday November 4 at 12:01 CST, and mocks an existing GitHub
  alert. After the correction all seven on-site sources remain unknown, the
  report returns 1, and no GitHub request occurs. It uses no live service.
- The publication-source regression also covers successful and unspecified
  chain outcomes, and partial history retaining CBS's published Week 8.
  A successful rebuild alone is not evidence that its publication completed.
- `python3 -m unittest tests.test_source_lateness tests.test_source_health_release`:
  36 tests pass. Existing coverage includes fully current alert resolution,
  known late sources remaining warning-only, unknown publication metadata,
  delivery failures, issue pagination and late/stale agreement.
- The existing served-week assertion now requires a missing ESPN publication
  to stay absent instead of accepting a candidate fallback. This strengthens
  the assertion to the corrected publication-provenance contract; no tests,
  holds, parity guards, freshness thresholds or pipeline gates were weakened.
- `git diff --check` passes. The source change removes candidate fallback
  only; the function signature and `--status` option remain compatible.
- Ownership reconciliation checked all 43 open PR changed-file inventories
  and the JEG-1200/JEG-1201/JEG-1479 claims. The four scoped paths do not
  overlap the active JEG-1176/#1304 repair.

### Claimed, not confirmed

- Required full validation, exact-head CI, independent review and release are
  pending the parent coordinator's normal sequencing. No competing heavy
  validation ran in this lane.
- No production or live recovery is established by these offline tests.
  History transactions, season validation, final capture ordering and the
  live verification target remain separate audit follow-ups on JEG-1485.

No production data, Supabase, access, workflow, value-math or engine changes
are included. No deployment, merge, deletion or blocked-host request occurred.
