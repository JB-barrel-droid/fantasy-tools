## 2026-10-22 - JEG-925 Research post: How position weights work

- Wrote research post 09 (`docs/research/posts/09-how-position-weights-work.md`) explaining the derivation of position weights from VP-2 through VP-5 (mixes, DDF weights, budgets), with a worked example using ESPN at PPR/12.
- All numbers recomputed from the Python reference (`pipelines/value_reference.py`, `Setting(Inputs.load(), scoring='ppr', teams=12, expected_starts=True).result()`) on the week 7 fixture. Eight-group sum verified = 1.0000.
- Sensitivity tables across 8/10/12/14 teams, PPR/Half/Standard, and superflex run from the same pipeline.
- Per-source mixes from all five included sources (FantasyCalc, CBS, ESPN, CBS ROS, Razzball).
- Drafted 120-word dashboard explainer; suggested placement in the v2 "How values work" tab.
- No code/doc disagreements found for the weight derivation itself. The methodology spec (VP-3, VP-4) matches both `value_reference.py:_mixes()` and `value_reference.py:ddf_weights()` and the engine's VP-4 block in `value-model.js`.
- Updated `docs/research/README.md` with post 7 entry.
- Verified: eight-group sum = 1.0, budgets = pie x weights, per-source group totals match code output. Not verified: approximate sensitivity percentages (2-3% per 1-point shift), 12-combo sweep not run (no engine code changed).
- Claimed, not checked: full `make validate` (no code changes, only docs).
- Jeremy decisions (2026-10-23): title is "How we split value across positions"; dashboard explainer goes as a collapsible section in the "How values work" tab, no separate card. UI implementation is a follow-up ticket under JEG-925.

## 2026-10-25 - JEG-925 refresh after #867 (PR #837)

- Merged origin/main (bd345e00) into `research/position-weights` (merge commit, no rebase). #867 (JEG-969) turned flex-filled bench seats and the promotion model on by default, so every figure in the post was stale (PPR/12 QB bench seats 15 -> 4).
- Recomputed every number in `docs/research/posts/09-how-position-weights-work.md` from `pipelines/value_reference.py` on the current fixture (`data/fixtures/current/`, built 2026-09-19): the 8-group table, budgets, ESPN group totals and worked example, per-source starter mixes (now seven sources, was five), league-size, scoring and superflex tables, bench-depth and roster-shape figures, and the sensitivity section. Prose that rested on those numbers was rewritten (QB share no longer "rises with league size", superflex "more than triples", sensitivity per 1-point shift is 1 / share, not "2 to 3 percent").
- Corrected a roster error in the draft: the default roster is QB1 RB2 WR2 TE1 FLEX1 with 7 bench, not WR3 and 6 bench.
- Dropped the "week 7" label: the fixture does not state its week (built 2026-09-19).
- Fixed the post 9 row in `docs/research/README.md`: it now sits inside the Post drafts table and points at the file; the stray duplicate row below the table is gone.
- Verified (run): eight-group sum = 1.000000 and budgets = pie x weights (max error 0) at all 24 combinations of 3 scorings x 4 league sizes x no/one superflex; per-source weights = group total / group sum; DDF weights = mean of the seven sources' weights; sensitivity re-run with `position_shares` (RB +13.4%, WR -9.8%, QB/TE unchanged).
- Not verified: browser engine against these figures (reference only; no engine or value code changed); bench-rule fit errors in the post (quoted from `bench-rule-research.md`, run on the 2026-10-10 engine); the fixture's week.
- PR left open for Jeremy's review of voice and accuracy. Not merged.
