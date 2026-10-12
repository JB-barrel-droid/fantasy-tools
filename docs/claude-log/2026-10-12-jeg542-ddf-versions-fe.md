## 2026-10-12 - JEG-542 three DDF Value versions in the v2 front end

Contract: GL-09 front end of JEG-497. Customize, the grouped picker (Rank by, Risers & fallers, Compare "Player values shown"), Player values, Compare and Targets carry "DDF Value", "DDF Value · trade charts" and "DDF Value · projections". Blended on by default, the other two off.

### What changed
- app/v2/v2.js: `DDF_VERSIONS` / `isDdfKey` / `ddfEntry` replace the 39 `DDF_KEY` sites that meant "the DDF Value". `ddfShown` (boolean) became `ddfShownSet`; `ddf.v2.selection` already stores the shown keys, so the versions persist with no format change (old saves load with the versions off).
- Customize: each version has its own row and its own inputs list under it (blend: all inputs; trade charts: the four charts; projections: the three projections). The inputs are one shared choice in the engine (`setCompositeInputs`), so a tick under one version moves the same input under the others. The blend's boxes keep `data-ddf-input`; the other two use `data-ddf-version-input`.
- "◐ 1 source" is per version, from `row.ddfByVersion[...].lowConfidence`.
- Tier for a version other than the blend: no engine tier exists, so it is the player's rank by that version against the blend's starter and bench counts in the same rows (display mapping, no value math).
- app/v2/movers.js: Risers & fallers series list now starts with the three versions (the engine's `getPriorWeek` already priced them). app/v2/targets.js: Our value offers the three versions.
- Compare: "Player values shown" offers all three; a picked version that is not shown in Customize joins the trade table.
- app/trade-value-chart/assets/curve-widget.js: `isLockKey` accepts `ddf_value_charts` and `ddf_value_projections`, so `setLockOrder` (Rank by) stops refusing them. `lockSourceAvailable` and `selectedRankSourceKey` already handled them. No value changes.
- Tests: new tests/test_v2_ddf_versions_render.py (defaults, names, inputs under each version, table cell equals `row.values[version]`, pickers on all four tabs, Rank by a version, reload, per-version one-source tag; three deliberately broken builds). GL-09 gets a real `partial` check in tests/test_v2_contract_render.py. Two string anchors in tests/test_v2_ddf_render.py's mutation list were updated to the renamed code (the mutations are unchanged in meaning). tests/test_v2_targets.py: the pinned `OUR_KEYS` list changed because GL-09 now says the versions are offered on every page.

### Decision (recommended default, Jeremy not asked)
- The feature-contract mirror still says "to build: JEG-497" because the Google Doc is the source of truth and the mirror says never to hand-edit it. GL-09's check runs now as `PENDING("JEG-497", partial=gl09)`. Follow-up for Jeremy: in the next contract revision, drop "to build" from GL-09 and point the line at JEG-542, then switch the check from `PENDING` to `gl09`.

### Verified (check named)
- tests.test_v2_ddf_versions_render (new, both tests), tests.test_v2_ddf_render, tests.test_v2_targets, tests.test_v2_movers pass.
- `make validate` (py3.12): see the PR for the exit status.

### Claimed, not confirmed
- The 12-combo engine sweep was not run: no value, curve or ranking math changed (the only engine edit is the lock-key allowlist), and `fixedPieIndexed` is untouched.
- The tier shown for the two non-blended versions was not compared against any reference; it is a display mapping from the blend's counts.
