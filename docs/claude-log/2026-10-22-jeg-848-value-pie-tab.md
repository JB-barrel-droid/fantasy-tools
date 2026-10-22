## 2026-10-22 - JEG-848 Value pie tab

Ticket: JEG-848 (child of JEG-847, Values auditing)
Branch: fe/JEG-848-pie
PR: #802

Implemented the Value pie tab for the Values auditing section. Cross-source
comparison of Adjusted value distribution by position (QB/RB/WR/TE) and role
(starter/bench). Four sections: total pie summary, by-position adjusted values,
raw vs adjusted slices, coverage analysis. Flag rule marks sources >10% from
cross-source median on per-rosterable-slot or per-player-posted values.

### Fixes applied (review round 1)

1. **Raw column bug (Point 3):** Changed raw values from per-player
   starterSlice+benchSlice sums (which equal adjusted when rates=1.0) to
   groups[pos|role] from valuePipelineDiagnostics (value-model.js:841-842).
   These are the pre-rescale group totals. Differ from adjusted whenever
   rate != 1.0 (rate = funded/groups, value-model.js:983).

2. **VP-5 fixture bug (Point 2):** Rebuilt test fixture so both sources'
   player adjusted values sum exactly to pie (1200). Source A (espn) has
   rates=1.0 (raw==adjusted). Source B (fantasycalc) has rates!=1.0
   (raw!=adjusted, proving the raw column works). Added VP-5 invariant test
   with negative test (tamper one player's adjusted, verify VP-5 breaks).

3. **Verdict rows (Point 4):** Added per-cut verdict rows: "Starters: spread
   X%, within 10%: yes/no" for starters, bench, total at the summary level
   and per-position. One-glance answer format.

4. **Real-data screenshots (Point 1):** Screenshots rendered against real
   engine output (all 7 sources, week 7, pie=2352). Saved to
   /Users/botcomp/code/fantasy-tools-selfhost-notes/jeg848-{desk,phone}-pie.png.

### Verified (check named)

- 31 tests pass with RENDER_TESTS_REQUIRED=1 (test_audit_pie.py): extract
  parity, VP-5 invariant, raw-vs-adjusted separation, flag computation,
  verdict computation, desktop 1440px and phone 375px render, negative tests.
- Desktop render: 13 tables, verdict rows, no horizontal page overflow.
- Phone render (375px): tables scroll within containers, no page-level overflow.
- Engine parity: tab totals match sum of player .adjusted from fixture.
- VP-5: each source's totalAdjusted == pie within rounding. Negative-tested.
- Raw vs adjusted: fantasycalc (rates!=1.0) raw differs from adjusted;
  espn (rates==1.0) raw equals adjusted. Negative-tested.
- Verdict rows: >= 15 verdict rows rendered, containing "spread" and "within".

### Not verified

- `make validate` not run locally (Mac overloaded). CI runs it on the PR.
- Integration with the shell (JEG-847) -- needs rebase onto fe/JEG-847-shell.
- Live render in the full app (waiting for shell integration).

### Design decisions (Jeremy, 2026-10-22)

- Active league setting only (follows the page's current settings).
- Show raw (pre-index) slices alongside Adjusted pie.
- Show players posted and players rosterable per source, and pie per player
  posted and per rosterable slot.
- Flag rule: >10% from cross-source median, shown with the number.
- Missing values never zero; source that posts fewer players says so.
- Every number from the engine's runValuePipeline result; no second calculation.
