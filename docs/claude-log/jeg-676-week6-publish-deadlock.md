# JEG-676: week 6 not published (fidelity-hold deadlock)

**Date:** 2026-10-15
**Ticket:** JEG-676

## Finding
- Site last published 2026-10-12 22:34Z (week 5). The rebuild chain failed in every one of the last 100 runs (no success). 10-13 cause: test_games_remaining parity; current cause below.
- The pulse held all 7 sources: freshness was red because the live chart is week 5 while stored rows already have week 6 (also ESPN: chart 4 d old, stored snapshot 10-15). fidelity_hold marks them held, the engine includes no source, and `make validate` fails on `test_spec_reference_value_pipeline.LiveDump` (`included == []`). Publishing is the only cure for the red, so nothing could publish. Reproduced locally by applying the committed pulse's holds.
- cbs and fantasycalc are also review-held by the chain (native_drift warn on a newer publication); these keep week 5 sections.

## Change
- `pipelines/fidelity_pulse.py`: freshness (week-based and projection) is amber, not red, when the stored rows are already as new as the publisher (the lag is the pending publish, not old data). Projection freshness judges the newest stored snapshot when it is newer than the chart's.
- `tests/test_fidelity_pulse.py`: two regression tests; both fail with the change reverted (checked).
- `tests/test_fidelity_hold.py`: three tests asserted combos stripped; JEG-569 part 2 (2026-10-12, PR 530) keeps combos by design, so the assertions were wrong. Fixture now carries combos.

## Verified vs claimed
- Verified: test_fidelity_pulse + test_fidelity_hold green; with the pulse holds reduced to cbsros/razzball/fantasycalc, LiveDump and test_seeded_hold_build pass.
- Claimed: chain publishes after this; test_asset_load_retry is correctly red until week 6 publishes and is untouched.
