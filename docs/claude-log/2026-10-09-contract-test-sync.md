## 2026-10-09 - Feature contract test, second pass (JEG-506)

Follow-up to `2026-10-09-contract-test.md` (the first pass landed on main as b2573e4a). This pass brings the test in line with the full JEG-506 brief.

### What changed
- `scripts/sync_feature_contract.py` (new): takes the exported Doc text (file path or `-` for stdin) and writes `docs/feature-contract.md`. No Google auth: it only cleans the export (Markdown escapes, whitespace-only lines, blank runs) and adds the header "Mirror of the Google Doc (source of truth): <url>. Regenerate when the Doc changes; never edit this file to change the contract."
- `docs/feature-contract.md`: regenerated with the script from the Doc v1.1 export (Drive connector, 2026-10-09). The text of every line matches the earlier hand-made mirror (word diff: only the header and layout changed). 57 IDs.
- `tests/test_v2_contract_render.py`:
  - `CHECKS` now holds every ID: a check function, or `PENDING("JEG-xxx", partial=...)`. The mirror test also fails when a "to build" line has a live check, or when its ticket differs from the Doc.
  - TT-05 is `PENDING("JEG-510")` through `WORDING_HOLDS` (the Doc line is live, but the UI says "indexed" until JEG-510). A partial check covers the ⓘ and the scale word.
  - GL-17 is `PENDING("JEG-500")` with a partial check: Player values (JEG-483) expands the chart and the table.
  - GL-11 (coordinator, 2026-10-09):
    - The league buttons are found by ID (#v2EditLeague, #v2Weights), not label. "Weights & bench" becomes "Position weights" in JEG-537.
    - "Edit league is the primary control" is held in `SUBPART_HOLDS` on JEG-498, because no primary styling exists yet. The DOM-order check is removed.
    - What is checked now is that league edits stay a draft until Apply.
  - Stronger checks:
    - GL-02 also compares Trade targets "Our value" and the top three Risers (before, now, change) with the engine.
    - GL-11: a league draft does not reach the engine (`getState().teams`) before Apply.
    - GL-15 covers each chart's own top 25.
    - MF-01: the Manifesto has no links.
    - TT-06: a chart is badged "Wk N" only when it is on an older week, and the badge shows that week.
    - GL-03: the tag reads exactly "◐ 1 source". The old string check was vacuous: the tag is a child span, so own-text never contained it.
  - New fixture `LOW_CONFIDENCE_FIXTURE`: Week 5 has no one-source DDF Values (0 of 738), so GL-03 and TT-08 could not see the tag. Every fifth priced player is flagged one-source in `getRows` / `getAllRows`; values are untouched. GL-03 and TT-08 now fail if the fixture finds no player to flag, so they cannot pass vacuously.
  - Broken builds: 13 faults over 11 IDs in three grouped runs. Each must produce a real finding; a check that crashed does not count.
- `docs/v2-design-notes.md`: new section "Feature contract test (JEG-506)" covering how the test works and the workflow rule.

### Verified
- `python -m unittest tests.test_v2_contract_render`: mirror tests (3) and the positive render test pass. The positive render test takes 62 s here; the target was under 4 minutes.
- Each broken build is caught by its check:
  - MF-01: nav reordered.
  - MF-01: Manifesto section 1 dropped.
  - CT-01: Swap hidden.
  - GL-01: "Vegas" in the header.
  - PV-02: the DDF line drawn at 2 px.
  - PV-09: Reset no longer restores Rank by.
  - GL-04: the prior-week status has no ⚠.
  - GL-05: the chip has no ⚠.
  - GL-05: the chip always says "all sources current".
  - GL-03 and TT-08: `isLowConfidence` forced false.
  - GL-08: Rank by defaults to the first active chart. The first version forced "espn", which became a no-op after JEG-508, because ESPN is no longer active by default.
  - GL-13: `.v2-wrap` min-width 480 px under 500 px.
- After sync, all 18 `tests/test_v2_*_render.py` suites ran one at a time on Windows, and all passed. That includes test_v2_ux_render and test_v2_panels_render, which failed only on the Mac in the first pass.
- `test_launch_front_door` passed.
- `python scripts/validate.py` passed 67/67, after renaming the script's `clean()` to `tidy_export()` because `test_one_name_resolver` reads a `clean*` function as a player-name normalizer.
- Full `tests.test_v2_contract_render` after the GL-11 change: 5 tests passed in 153 s, broken builds included.

### After rebasing onto main (e85488af, which includes JEG-508 #491)
- `tests.test_v2_contract_render`: OK, 5 tests in 145 s. Every live contract line still holds on the source-neutral engine.
- `validate.py` passed 63/63, and `test_launch_front_door` passed.
- Six v2 suites fail on main. This commit does not touch their code (app/v2, curve-widget.js, or their tests), so the failures come from JEG-508's engine change. They are not in the deploy gate (`make validate`).
  - test_v2_bench_used_render: `Cannot read properties of undefined (reading 'calibration')`.
  - test_v2_compare_render: "the trade has no player missing…". This is a fixture assumption.
  - test_v2_how_render: "copy carries numbers not from t…".
  - test_v2_offer_render: "no shown series lacks a value…".
  - test_v2_targets_render: the broken build "missing read as zero" is no longer caught.
  - test_v2_waterfall_render: the broken build "verdict names no source" is no longer caught.

### Claimed, not confirmed
- TT-06's badge branch only runs when a chart is on an older week in the served data. I did not confirm whether any chart is on an older week in the Week 5 data, so the badge side may not have run.
- RF-01's "could not compare" count only applies when some players could not be compared.
