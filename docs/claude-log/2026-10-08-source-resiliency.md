## 2026-10-08 - Source resiliency (feat/source-resiliency, decision source-resiliency-001)

Contract (Jeremy, pre-launch): "have resiliency for when some of the sources
fail". One source failing must not take down or corrupt the site: the others
publish, the failed one keeps its last good promoted section with an honest
older-week label, nothing shows a missing value as zero, and a failed ESPN
anchor refresh keeps the last good anchor.

### Failure-mode matrix (before -> after)

Sources: usatoday, fantasycalc, fantasypros, cbs (published charts, review
gated), espn (anchor, DDF legs), cbsros (DDF legs), razzball (imported here,
section built outside this chain; razzball-refresh branch adds it to the chain).

| Failure | Before (origin/main 196906f) | Site impact before | After |
| --- | --- | --- | --- |
| Ingest workflow fails / publisher blocked (USA Today 402), Supabase table empty or unreadable for one source | `import_supabase_references.py` exits 1; the import loop runs under `bash -e`, so the step and the job end. No chain, no fixture commit. | Every source stops updating; only status/health files commit. | Loop warns and continues. The source has no fresh snapshot -> chain halts it at `snapshot` -> isolated, last section kept, labelled older week. |
| Import of razzball fails | Same as above (razzball is in the loop) | Whole refresh stops | Warn, continue. |
| verify_import_health red / crashes | Non-blocking since 2026-10-07 (warning) | None | Unchanged. |
| match / reference / section / reindex fails for one chart source | ChainHalt -> source `failed` -> whole chain fails, fit/_adjusted skipped, fixture not committed | Every source stops updating | Isolated: fixture restored to bytes from just before that source ran (half-promotions rolled back, promotion records renamed); others publish; fit and _adjusted run. |
| Review hold | Isolated (per-source-promotion-001) | Held source older week | Unchanged. |
| Review malformed (garbage verdict, no artifact) | Whole chain fails | Every source stops | Isolated. |
| Promote refusal (L1 import gate, provenance) mid-source | Whole chain fails; first section was already merged on disk (not committed) | Every source stops | Isolated, half-promotion rolled back. |
| Stage script crash (exception, timeout) | Whole chain fails | Every source stops | Isolated. |
| Identity-resolution collapse | Matcher sends rows to review; a short section -> review hold (isolated) or match failure (whole chain) | Mixed | Isolated either way. |
| ESPN snapshot/leg/section/review failure | Whole chain fails; new legs left on runner | Every source stops; anchor kept (nothing commits) | ESPN section AND DDF legs restored byte-for-byte; other sources reindexed against the kept anchor; fit runs. If a fresh ESPN bake ran, the workflow restores the committed CSV/players.json/manifest before `make validate`, so a fresh bake never ships beside a kept ESPN section. |
| ESPN bake (players.json) fails | `continue-on-error`; restore step checks out the committed anchor | None (last good anchor) | Unchanged (verified by tests/test_rebuild_chain_bake). |
| cbsros leg/section failure | Whole chain fails | Every source stops | Section and legs restored; others publish. |
| Every review-gated source fails/holds (Supabase outage) | Whole chain fails | Site keeps last build | Unchanged: still fail-closed (nothing new to publish). |
| Re-translate / fit / _adjusted failure | Whole chain fails | Site keeps last build | Unchanged: shared stages, not a single source; publishing raw sections with stale adjusted curves would mislabel weeks. |
| Restore cannot be verified | n/a for non-holds | n/a | Fail closed (chain red, nothing commits). |
| `make validate` red after the chain | Chain step failure; status only | Site keeps last build | Unchanged (wrong numbers block). |
| Consolidation write fails | Non-blocking (consol-nonblocking-001) | None | Unchanged. |
| Commit rebase conflict / Pages dispatch fails | Job fails loudly; site keeps last deploy | Stale | Unchanged. |
| Snapshot dir `week-10` vs `week-4` | Name sort picks `week-4` (committed fantasycalc snapshot in CI) from Week 10 | FantasyCalc/CBS rebuilt from old week -> L1 refusal -> whole chain red every run | Chronological sort. |
| Browser: `assets/consolidated-values.json` 404 (live today) | consolidation-index falls back to deriving from the fixture | None | Unchanged. |
| Browser: player-news / reference-freshness / adjustment-inputs 404 | Optional fetches (`.catch(()=>null)`) | News columns empty | Unchanged. |
| Browser: a held/failed source's kept section | product-data freshnessLabel reads the section's own week | "Older week" card + header count | Unchanged (verified headless). |
| Browser: a source section missing from the fixture | product-data refuses render; validate red, so it never deploys | Deploy held, live site keeps last build | Not changed (GAP-MISSING-SECTION-REFUSES-RENDER). The chain can no longer produce it. |

### Verified (named checks)
- `python3 -m unittest tests.test_rebuild_chain_source_resiliency`: 17 tests
  OK on the branch. With origin/main's `rebuild_comparison_chain.py` and
  `rebuild-chain.yml` swapped in, all 10 failure-mode tests FAIL and the 7
  negative/guard tests ERROR (symbols absent) -- every failure-mode test fails
  on main.
- Negative tests catch: all-or-nothing on failures (FAILURE_ISOLATED_SOURCES
  = ()), section-only restore without legs, name-sorted snapshots, the old
  fail-fast import loop, removing the bake revert.
- `python3 -m unittest discover -s tests -p "test_rebuild_chain*.py"`: 100 OK.
- Three tests in tests/test_rebuild_chain_per_source_hold.py pinned the old
  rule (a non-hold failure / an ESPN failure fails the whole chain). Changed
  because Jeremy changed the rule (2026-10-08); `test_isolating_a_non_hold_failure_is_caught`
  was removed because it no longer guards anything (a non-hold failure is
  meant to be isolated now).
- Headless Chrome on the built dist (scratch probe, not committed): baseline
  has 0 page errors with consolidated-values.json 404; a copy with USA Today
  relabelled Week 4 shows "USA Today: Week 4 · newer week not yet published",
  status older, header "5 of 10 on an older week"; adjustment-inputs 404 and
  player-news 404 copies: 0 page errors, all cards render; a copy with the
  usatoday section removed: render refused (recorded as a gap).
- `make sync`; `CHROMIUM_PATH=... make validate` exit 0.

### Claimed, not confirmed
- The real stage scripts behave like the fakes on these failures (faked
  stages only; no local data/raw snapshots and no Supabase key were used, and
  no production workflow was dispatched).
- A real ESPN failure in CI followed by the bake revert yields a green
  `make validate`: if other sources' new sections reference player keys only
  in the fresh players.json, validate goes red and nothing publishes
  (fail-safe, not wrong numbers). Not exercised.
- razzball: legs are registered for restore (`LEG_FILES`); it only runs in
  this chain once the razzball-refresh branch adds it to SOURCES.
