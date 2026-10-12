## 2026-10-12 - JEG-598 decisions back-fill

Contract: record decisions made only in Linear comments since 2026-10-07 in docs/decisions.md with Jeremy's quotes and dates.

### Verified (check named)
- Quotes were copied from the ticket text read through the Linear API on 2026-10-12: JEG-533 comment (es-value-001), JEG-556 comments and description (roster convention, K/DEF), JEG-563, JEG-510, JEG-497, JEG-502, JEG-505, JEG-543, JEG-625.
- Entry shape: each new entry has the front-matter keys, Context, Problem, Options, Recommendation and Outcome Note sections like the existing entries. Checked by eye against the Entry Format section; no validator test exists for decisions.md (grep of tests/, tools/, pipelines/ found none).

### Claimed, not confirmed
- Not backfilled: "use canonical resolver" (source ticket not located), Jeremy's answers on the starter line and short-list waiver line (JEG-556 decisions 3 and 4; not found in the comments read, flagged in the roster-convention-001 note).
- Risk register two-way match to tickets (every fidelity finding has a row and a status, no row without a ticket) was not done in this PR; JEG-598 stays partially open on that point.
- Only a first page of JEG-556 comments (8 of more) and the first page of a "decision" ticket search were read; other decisions may exist.
