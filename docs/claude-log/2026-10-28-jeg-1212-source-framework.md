# JEG-1212 source framework draft

## Verified

- Added a read-only source taxonomy and two comparison recipes with stable IDs, role/scale/aggregation/coverage metadata and explicit input states. The published-chart mean requires all three indexed inputs; numeric zero counts, a below-depth zero with an explicit reason is marked unlisted, an unannotated zero has unknown listing ancestry, null stays unavailable, and estimate ancestry is reported. `node tests/node/source_views_check.mjs` passed and is wired into `test-core` and its CI shard.
- Split the existing value chart, table columns and Customize source labels into projections, published charts, and observed-trade estimates. The observed-trade source keeps its existing identifier. `CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_v2_source_count_render` passed after its old combined-label assertion was updated for the explicitly approved category split. It still checks the exact Trade targets source keys.
- The local rendered player detail showed Gibbs at 52.5 for the published-chart average and 68.6 for the observed-trade estimate; there were no page errors. The existing DDF default, inputs, engine, fit, verdict, and saved identifiers were not edited.
- `tests.test_v2_rescaled_copy` passed after its October 9 ban on the words “published chart” was narrowed. That ban became wrong when Jeremy selected “Published charts” as a category; the test still rejects “as published” and “indexed” as reader-facing transformation labels.
- `python3 -m py_compile pipelines/build_v2_page.py`, `node --check` on the changed JavaScript, and `git diff --check` passed.
- `CHROMIUM_PATH=/usr/bin/chromium make test-core` completed green. The broad `test_view_invariants` matrix passed 15 settings and 270 checks with no problems; `test_main_table_engine_parity`, DDF composite, and view-switch default tests passed. The source-view unit, copy guard, CI shard integrity, and focused browser source-count guard were rerun after the final presentation edits and passed.
- After rebasing on current `main`, `CHROMIUM_PATH=/usr/bin/chromium make validate-base` passed. Its strict reference/engine comparison agreed on 1,234,996 values; the focused browser source-count guard and lightweight tests also passed on the rebased commit.
- The v2 contract render's GL-07/GL-21 partial checks were updated for Jeremy's later JEG-1212 category decision: they require the Published and Observed groups, retain the rescaled meaning check, and still reject an "as published" mutation. The historical Doc mirror was not edited. Its live-contract test passed locally after the update.

## Claimed, not confirmed

- Formal live 12-combo QA, all populated tools, and production behavior were not tested. The private JEG-1212 article is still a draft; this branch does not publish it.

## Scope and follow-up

This branch owns `app/v2/source-views.js`, the source group labels, table grouping and Values-only player-detail comparison in `app/v2/v2.js`, the page builder's script registration, and focused tests. Player detail explains Rank by, the DDF basis and the comparison-only role of the new readouts. The comparison is omitted from Risers because its shared drawer can receive a mixed-week row. It does not change interactive Compare's controller, `finder.js`, `workspace.js`, value math, or connector responses. Those surfaces need separately coordinated wiring and approval where they would change behavior. The visual design remains unselected; keeping Values prominent and chatbot parity are design/connector follow-ups, not a palette or production rollout here.
