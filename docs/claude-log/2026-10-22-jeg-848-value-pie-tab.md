## 2026-10-22 - JEG-848 Value pie tab

Ticket: JEG-848 (child of JEG-847, Values auditing)
Branch: fe/JEG-848-pie
PR: #802

Implemented the Value pie tab for the Values auditing section. Cross-source
comparison of Adjusted value distribution by position (QB/RB/WR/TE) and role
(starter/bench). Four sections: total pie summary, by-position adjusted values,
raw vs adjusted slices, coverage analysis. Flag rule marks sources >10% from
cross-source median on per-rosterable-slot or per-player-posted values.

### Verified (check named)

- 19 tests pass with RENDER_TESTS_REQUIRED=1 (test_audit_pie.py): extract
  parity, flag computation, desktop 1440px and phone 375px render, negative
  tests for zero-for-missing and wrong-sum.
- Desktop render: tables render, no horizontal page overflow, flags visible.
- Phone render (375px): tables scroll within containers, no page-level overflow.
- Engine parity: tab totals match sum of player .adjusted from fixture for every
  source, every position, every role.
- Negative tests: extract correctly returns null (not 0) for perListed when
  listed=0; position totals sum to source total (catches double-counting).

### Not verified

- `make validate` was started but timed out (tests were passing up to that
  point; only new files were added, no existing files changed).
- Integration with the shell (JEG-847) -- branch fe/JEG-847-shell not yet
  pushed. Needs rebase onto that branch.
- Live render in the full app (waiting for shell integration).

### Design decisions (Jeremy, 2026-10-22)

- Active league setting only (follows the page's current settings).
- Show raw (pre-index) slices alongside Adjusted pie.
- Show players posted and players rosterable per source, and pie per player
  posted and per rosterable slot.
- Flag rule: >10% from cross-source median, shown with the number.
- Missing values never zero; source that posts fewer players says so.
- Every number from the engine's runValuePipeline result; no second calculation.
