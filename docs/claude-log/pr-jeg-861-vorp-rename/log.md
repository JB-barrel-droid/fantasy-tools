## 2026-10-23 - JEG-861 User-facing VORP renamed "Value above waivers"

Contract: decision copy-vorp-002 (Jeremy, 2026-10-22, option b). Every
user-facing label for VORP becomes "Value above waivers" (raw series:
"<source> value above waivers, raw"). Internal keys, the `vorp` view ID, CSS
classes, element ids and URL state are unchanged.

Branch `fe/JEG-vorp-rename`, resumed from uncommitted edits on old main
9f6d4062; committed the source edits, then plain-merged origin/main f340dfa9
(no conflicts).

### Changed (source only)
- `app/trade-value-chart/assets/{curve-widget,comparison-dashboard,product-data}.js`
  and `app/trade-value-chart/index.html`: these tracked files are the source of
  those widgets (no other copy), so only the label hunks were kept.
- `app/inspector/{math-inspector.js,shell.html}`, `app/v2/{v2.js,shell.html}`,
  `app/values-explainer/template.html`, `modules/{consolidation,dashboard}.html`,
  `pipelines/build_pipeline_checkpoints.py`, docs (`decisions.md` adds
  copy-vorp-002, `feature-contract.md`, `architecture-target.md`).
- Restored as generated churn, not committed: all of `dist/`, the build stamp
  and `?v=` query strings in `index.html`, `comparison-sources-data.json`,
  `reference-freshness.json`, the players-data/methodology-data blobs.

### Tests changed because the label is the thing renamed
`test_public_copy_no_vorp.py` (now bans "vorp" in widget string literals and
sweeps rendered text and accessible names), `test_jeg38_raw_vorp_sources.py`,
`test_razzball_production_followups.py`, `test_source_freshness.py`,
`test_static_export.py`, `test_v2_{contract,how,panels,states}_render.py`:
assertions on the old strings "VORP vs waivers" / "raw VORP" now assert the new
label. No threshold or data assertion was changed.

### Verified / claimed
See the PR body for the test run result. Remaining "VORP" in `app/` is code
comments and internal identifiers only (checked with `git grep`).

### Test results (named)
Run on system python 3.9.6, dist temporarily patched with the renamed source
files (restored afterwards; dist not committed). Passed: test_public_copy_no_vorp,
test_jeg38_raw_vorp_sources, test_razzball_production_followups,
test_source_freshness, test_static_export, test_vorp_wiring, and every
`test_v2_*render` file except those below (including contract, how, panels,
states, targets_combos, writing_routes, expand, compare).
Failing here AND on an untouched origin/main f340dfa9 worktree (so not caused by
this change): test_v2_circular_banner, customize_cleanup (4), ddf_versions,
held_chip (2), nav_320, plain_copy (guard_fails_on_broken_builds), source_count,
targets (rendered_numbers_and_layout), waterfall. Likely stale-dist or
environment related; not investigated.
Claimed, not checked: the lowercase label inside long sentences in the patched
dist was a blunt sed, so dist-based render checks of mid-sentence casing are
only as good as the source copy in app/trade-value-chart/index.html.
