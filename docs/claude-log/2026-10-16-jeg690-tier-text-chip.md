## 2026-10-16 - JEG-690 v2 tier text read "StarterStart"

Root cause: JEG-571 chips (PRs 634/639/640) were appended inside `.player-sub` / `.v2-meta`, so the sub-line textContent ("QB · KC · Starter") ended in the chip text. Code was wrong, tests read the right element.

### Changed
- `app/v2/v2.js`: `subWithTag` wraps the sub-line and the chip in `span.v2-subrow` (chip is a sibling). Used in the Player values name cell, Trade targets table and phone cards. Drawer meta line unchanged (chip still inside `.v2-meta`; no test flags it).
- `app/v2/v2.css`: `.v2-subrow` flex row, chip styling selector extended.

### Verified
- `tests.test_v2_contract_render`: no tier lines remain. `tests.test_v2_targets_render`: zero "tier" errors. `tests.test_v2_player_tags_render` ran in the same invocation as the contract suite; the only error there was a drawer-timeout in a suite that also ran the contract failures (not investigated further).

### Remaining reds (not tier text; not fixed)
- Contract GL-08, TT-03: assert default Our value = ddf_value; JEG-677 (#630) reversed it to ddf_value_projections. TT-04, TT-08: assert best-single-chart / one-source flags that JEG-677 replaced with consensus. Contract lines are stale vs JEG-677; need a decision/rewrite.
- Contract PV-20 (`rankOptions` KeyError), CT-03 (IndexError): checks could not run.
- test_v2_targets_render: probe simulation failures ("no sell target with two charts") and week-6 data.
- test_v2_panels_render: rows 41px vs ~32 expected at 1440/1366 (wrapped sub-line), More-from window label, CBS prior-week (week 6). The sideways scroll (127/66px) did not appear in the failure list on this run; no CSS change made for it.

### Claimed, not confirmed
- Row height 41px may predate this change (not compared against main).
