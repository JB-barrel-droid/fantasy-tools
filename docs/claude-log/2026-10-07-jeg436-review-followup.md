# 2026-10-07 - JEG-436 review follow-up: two false holds after #392

Contract: #392 (set-based coverage + tail-churn tolerance) merged, and the
14:38Z rebuild chain (run 37638380194) still held two sources: USA Today
`coverage:full_12/QB` ("candidate priced 32 < fixture 35 (dropped: none
named)") and FantasyCalc `coverage:full_12_qb1/TE` (Freiermuth + T. Ferguson
dropped, Gesicki added; "1 dropped player(s) still priced live (e.g. pat
freiermuth) -- pipeline loss"). The other four promoted. Find root causes on
evidence, fix without loosening a gate without evidence, negative-test.
Branch `jeg436-review-followup`; no Supabase writes (read-only SQL only).

### Verified (check named)
- **USA Today root cause: mixed basis in #392.** `c_n = combo["n"][pos]` is
  the flex-aware pie's bucket count; `reindex_comparison_section.py` excludes
  zero-native players from buckets (`zero_native`) but still stores them at
  0.0 in `reindexed`. `f_n = len(fx_priced)` counts the reindexed set. USA
  Today QB: 35 priced, 3 at native 0.0 (Fernando Mendoza, Shedeur Sanders, Tua
  Tagovailoa), recorded 32 -- on both the fixture and (per the CI detail
  "dropped: none; added: none") the candidate. Check: scratch script
  `repro_usa.py` builds a candidate from the published fixture section with
  `n` from `index_total.n_priced` and reviews it against the same fixture:
  origin/main reviewer -> `hold`, `coverage:full_12/QB:fail -- candidate priced
  32 < fixture 35 (dropped: none named; added: none) ... count fell by 3 but no
  player left the priced set` (byte-for-byte the CI message), same on half_12
  and standard_12; fixed reviewer -> `ready`.
- Fix: both sides compare priced sets when the fixture has one (recorded counts
  on both sides only when it does not). The candidate's own recorded n vs its
  own set is a new `coverage_count:{combo}/{pos}` WARN that states whether the
  zero-native exclusion explains the gap ("explained" / "UNEXPLAINED").
- Fixture survey (all sources, recorded n vs set vs zero-native): CBS and
  FantasyPros agree exactly; USA Today QB 32/35/z3 (explained); FantasyCalc
  QB 32/33, RB 59/60, WR 78/76, TE 28/27 with z0 (unexplained, stale
  index_total -- already the #392 `coverage_baseline` warn); ESPN differs by
  design. This is why the candidate-side check is a warn, not a fail: a hard
  fail on "unexplained" could re-hold FantasyCalc for a metadata reason.
- **FantasyCalc: publisher tail churn between bake and review, not a pipeline
  loss.** Evidence:
  - Bake run 37478103839 (fantasycalc-weekly-save, 2026-10-06 14:20Z) log:
    pulled 198 players per scoring, saved 585 rows (195 x 3), review notice
    names only Kenny Gainwell (identity), player_key 3081 Tyreek Hill and 3735
    Joe Mixon (reindex review). No TE was lost by the importer.
  - Supabase read-only SQL on `public.source_trade_values`, bake
    `fcwk5_2026-10-06_v1`: 26 TEs per scoring, min native 2.0 overall (no
    pipeline value cutoff); no Freiermuth, no T. Ferguson, Oronde Gadsden
    present (68 full). Earlier 10-05 15:02Z rows (bake_id NULL) had Freiermuth
    26, Ferguson 61. `public.players` has Freiermuth 786, T. Ferguson 2142,
    Michael Mayer 1382 -- identities exist.
  - Live API 2026-10-07 (`numTeams=12&ppr=1`): 198 players, 27 TEs;
    Freiermuth 27th and last at 20; Michael Mayer (51) present; Gadsden absent;
    T. Ferguson absent.
  - So the bake simply did not receive Freiermuth on 10-06 and the live list
    re-added him on 10-07 at the very bottom. The live check compared a
    24h-old bake to today's list.
- Fix: `verify_coverage_drop_live(..., pos, depth)` reads the live position
  and ranks it; a dropped player still live is a pipeline loss unless the live
  list ranks him BELOW the candidate's priced depth at that position (rank >
  depth). Those fall to the existing tail-churn rule (which still holds on
  identity loss, listed-but-unpriced, non-tail and >cap drops). Unknown live
  position, or no pos/depth, stays a contradiction (fail closed). Live
  reproduction (`repro_fc.py`, fixture minus the 2 TEs plus Gesicki, live API):
  origin/main -> `fail ... still priced live (e.g. pat freiermuth)`; fixed ->
  `warn ... pat freiermuth (live TE27/27) ... tail churn tolerated: net -1`.
- Negative tests (tests/test_review_coverage_churn.py,
  tests/test_review_coverage_live_verify.py): new tests run against
  origin/main's reviewer -> 5 FAIL + 2 ERROR. Mutant "candidate side back on
  recorded n" -> 4 FAIL. Mutant "every still-live player treated as below
  depth" -> 3 FAIL (incl. the pre-existing
  `test_live_contradiction_overrides_tail_rule`). Mutant "coverage_count warn
  removed" -> 3 ERROR. All pass on the fix.
- Pinned assertions changed (and why): `test_unnamed_count_drop_holds` and
  `test_count_below_named_set_holds` asserted a HOLD when the candidate's
  recorded n fell below an unchanged/near-unchanged priced set. That is
  exactly the mixed-basis defect that held USA Today with identical sets, so
  the assertion itself was wrong. They are now
  `test_recorded_count_below_unchanged_set_is_not_a_drop` (no coverage check,
  coverage_count warn, ready) and `test_count_below_named_set_is_judged_on_the_set`
  (tail churn warn on the set, UNEXPLAINED coverage_count warn).
- Non-fatal chain items from the same run: Stage 9 VORP refresh failed on
  `standard_8` (PR #390 covers it); Stage 10 lineage failed on
  `dist/modules/live-page-scrape.json` 109.5h old (scraped_at
  2026-10-03T01:07Z; last commit bdf43bd; no workflow runs
  `scrape_live_source_pages.py`) -- not in the register before; added
  GAP-LIVE-SCRAPE-STALE.
- `make validate` result: see the PR body (run before push).

### Claimed, not confirmed
- That the candidate USA Today section built in CI had the same 35-player QB
  set as the fixture: inferred from the CI detail "dropped: none named; added:
  none" (set difference empty both ways) and 32 recorded; the CI candidate
  file itself was not available locally.
- That FantasyCalc's 10-06 response lacked Freiermuth: inferred from 198
  pulled vs 195 saved with the 3 non-saved players named and none a TE; the
  raw 10-06 response was not kept.
- That the rank-vs-depth rule cannot mask a real loss of the LAST player at a
  position when the live list is unchanged: it can -- a pipeline loss of
  exactly the last-ranked player is indistinguishable from churn by this
  check; identity loss is still caught via review rows, and the tail rule's
  cap still applies.
- Post-merge chain outcome (USA Today and FantasyCalc promoting) not yet
  observed.
