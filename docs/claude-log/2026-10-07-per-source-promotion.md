## 2026-10-07 - Per-source promotion (decision per-source-promotion-001)

Contract: stop one source's review `hold` from failing the whole rebuild chain.
Sources whose review is `ready` publish; a held source keeps its last promoted
section, labelled with its own week; the hold is never overridden and stays
loud; an all-held run, a validation failure, or any non-hold failure still
fails closed. Branch `per-source-promotion`, worktree `~/code/wt/per-source`
off origin/main a5e2d8e. Not merged; no workflow dispatched; no Supabase write.

### Verified (check named)

- **Hold isolation works on a half-promoted source.** `tests/test_rebuild_chain_per_source_hold.py`
  uses a fake promoter that really merges into the fixture and restamps the
  whole section (as the real promoter does). FantasyCalc section a promotes,
  section b holds. After the run, `sources.fantasycalc` equals the pre-run
  section exactly, its rolled-back promotion record is renamed
  `*.rolled-back.json`, the other three review-gated sources are Week 5, fit
  and `_adjusted` ran, `success: true`, `outcome: published_with_holds`.
- **Negative tests, in-file (monkeypatched broken states), each caught:**
  all-or-nothing (`HOLD_ISOLATED_SOURCES = ()`), held-but-not-restored,
  held candidate pushed through promote, all-held run published, every halt
  treated as a hold, severity that never goes red, recorder that reports a
  hold as ok.
- **Source mutation run** (scratch `mutate.py`: apply one edit, run
  `python3 -m unittest tests.test_rebuild_chain_per_source_hold`, restore):

  | Mutation | Result |
  | --- | --- |
  | M1 `HOLD_ISOLATED_SOURCES = ()` (all-or-nothing) | caught (8 tests fail) |
  | M2 restore write and its sha verification both removed | caught (`test_half_promoted_held_source_is_restored_exactly`, `test_unverifiable_restore_fails_closed`) |
  | M2b restore write removed, verification kept | caught (chain fails closed: 4 tests fail) |
  | M3 chain lets a `hold` verdict reach promote | caught (`test_held_candidate_is_never_promoted` + 7) |
  | M4 `all_review_gated_held` always False | caught (`test_all_review_gated_sources_held_fails_closed`) |
  | M5 every review halt classed as a hold | caught (`test_non_hold_failure_still_fails_closed`) |
  | M6 severity always amber | caught (2 tests) |
  | M7 recorder: held check always ok | caught (3 tests) |
  | M8 recorder: stale check always ok | caught (2 tests) |

- **Existing guards unchanged and green:** `tests.test_rebuild_chain_failclosed`,
  `tests.test_build_lag_gate`, `tests.test_weekly_chain_espn_gate` (33 OK),
  `tests.test_rebuild_chain_workflow` (JEG-8 no-push-on-failure pin, unchanged),
  `tests.test_monitoring_coverage`, `tests.test_workflow_no_event_interpolation`,
  `tests.test_decisions_log`. No existing test was edited.
- **Display of a held source.** Ran the `tests/test_source_freshness.py` node
  harness (`cmd: freshness`, today 2026-10-07) on the shipped fixture with
  FantasyCalc forced to the week a hold would keep: Week 5 -> `current`;
  Week 4 -> `older`, `weeks_behind 1`; Week 3 -> `older`, `weeks_behind 2`,
  excluded on first load. `fantasycalc_adjusted` gets the same (it is dated by
  its raw source, and `build_adjusted_fixture_sections.py` copies the raw
  `week_designated`). A held section keeps its old `week_designated`, so it
  never displays as current. No app change was needed.
- **`make sync && make validate`** (CHROMIUM_PATH = local Chrome): on this
  branch it stops at `tests.test_static_export.test_known_full_ppr_12_team_source_values`
  (`25.5 != 25.3`). Clean origin/main a5e2d8e fails identically at the same
  test (baseline run before any edit). Every test-unit module after that stop
  point was then run individually on the branch: 26/26 OK
  (`test_two_tier_frontend` skipped=7). Stamp files reverted before commit.

### Claimed, not confirmed

- That the real promoter + real review in CI behave like the fakes. The fake
  promoter mirrors `promote_comparison_section.py` (merge + whole-section
  vintage stamp + built_at bump + promotion record); not run against real data
  here (no `data/raw` in this worktree).
- That the two monitoring checks record. `supabase/migrations/chain_source_holds_20261007.sql`
  is written but NOT applied; until it is, the recorder's insert fails the
  check_id foreign key (it logs a `::warning`, never fails the job) and
  health-artifacts' live coverage audit will report two gaps.
- Coherence when ESPN is involved: ESPN cannot be held (its gate is
  structural); any ESPN or cbsros failure still fails the chain closed. A held
  source's kept values were reindexed against the ESPN anchor of the run that
  promoted them; its `_adjusted` series is refit against the current leg. This
  is reasoning from code, not a measured comparison.
