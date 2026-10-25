## 2026-10-24 - Overrides tab: value basis and weights (JEG-1044)

Contract: build the basis-and-weights half of the Overrides tab from the decided spec (fantasy-tools-selfhost-notes/jeg-overrides-tab/spec.md, Amendment 1) on top of merged #894 (JEG-1035). Jeremy's decisions (2026-10-24): default = our methodology; presets Our methodology / one source / blend with integer-percent weights; Rescaled and Indexed follow the basis (labelled); player overrides global; Customize DDF blend tab removed and migrated; share links carry basis and overrides; ddf_value_projections stays the equal-weight reference; prior week on the current basis; live apply; persistent indicator with reset. Branch fe/JEG-1044-basis-weights.

### What changed
- Engine (value-model.js, curve-widget.js, value_reference.py, spec_reference/value_pipeline.py): `basisConfig` in the VP-6.3 blend (single source or weighted mean, per-player re-normalised); the Indexed basis is the blended value; `ValueModel.applyDdfOverride` is the one overlay for player overrides. `setBasis/getBasis/resetBasis`; `setCompositeInputs` is an alias. `value_check compare --basis`.
- UI: Overrides tab (basis picker above player overrides), indicator + Reset all + Undo in the league row, link banner, export/import, share params `basis=` / `ov=` (packed `z:` past 6 overrides, dropped past ~1800 chars with a message and an Export hint), localStorage v2 record with v1 and `ddf.v2.selection.inputs` migration, link settings in sessionStorage only. Rescaled labels, DDF copy and the auditing page say when the basis is not ours.
- Tests: tests/test_basis_overrides.py (3-way parity, 6 frozen fixtures basis_*.json, broken-build proofs), tests/test_basis_overrides_render.py (12-combo default identity against the frozen engine in tests/fixtures/baseline_main_61ecb39e/, basis math, pie), tests/test_v2_overrides_basis_render.py (rubric, task script, migration, links, a11y, phone, layout); seven existing DDF-blend render tests migrated (commit 1c9cb67b).

### Verified (check named)
- `python3 -m pytest tests/test_basis_overrides.py` 34 pass; JS, Python reference and spec reference agree on all six fixtures; default fixture is the pre-change engine's output.
- `value_check compare --rerun-engine --strict` default: 0 mismatches over 1.23M values; with a 3-source blend: agree.
- tests/test_basis_overrides_render.py 5 pass (12 combos x 5 bases: fixedPieIndexed, default byte-identical to 61ecb39e, chart average and projections reference unchanged).
- tests/test_v2_overrides_basis_render.py 17 pass.

### Findings / not verified
- The spec's "a chart used as the whole basis has Indexed factor exactly 1.0" is wrong (a uniform scale; Indexed total = Adjusted total over shared players). Tested instead. fixedPieIndexed holds for every basis, so it was NOT relaxed. sourceScaleAgreement was already retired (GAP-026).
- FantasyCalc-only basis: values agree with the Python reference but ~20 boundary players per setting flip tier/tag: engine adjusted 0 vs reference ~0.006 for sub-waiver tail players (pre-existing tail divergence inside the 0.05 tolerance), exposed because one chart as the whole basis makes `v == 0 -> waiver` decide tiers. Logged in the risk register.
- tests/test_value_pipeline_engine ExpectedStartsVariantTest fails on baseline 61ecb39e too (not from this change).
- Plain tab click from a Compare hash with a query reloads the page (pre-existing); link settings survive it via sessionStorage.
- Not built: +/- adjustment type for player overrides and per-value override flags on every tab (player-override half, JEG-1035 follow-up); a basis notice on Health check (#899 not merged) and the league workspace (not merged); both read rows, so they follow the basis, and listen to `ddf:league-settings-changed`.
