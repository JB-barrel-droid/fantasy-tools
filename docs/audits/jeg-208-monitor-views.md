# JEG-208 monitor view audit

Base: main63a884b. Findings posted to Linear before edits on2026-10-02.
The five reviewed sections now identify Indexed, VORP or Adj explicitly.

| Section | Actual evidence | Result |
| --- | --- | --- |
| Translation freshness | Legacy Supabase grain provenance/week | VORP legacy checkpoint; no Option C readiness claim |
| Index math | Native trade values from four publishers | Indexed target70/max rescale only; rendered wiring unverified |
| Scale agreement | Fixture reindexed/DDF vs ESPN peaks | Adj legacy diagnostic; no Indexed certification |
| Methodology consistency | Legacy reindex fit method/anchor | VORP/Adj legacy consistency; new shared model pending |
| Source lineage | Historical native, inferred VORP and rebuilt estimates | VORP/Adj legacy trace; new view columns belong to JEG-207 |

Indexed report never calls DDF verification or reads reindexed/translation/fit
values. Each exact native configuration gets its own factor. Genuine zero and
null stay zero and null; invalid values and nonpositive peaks are unavailable.
Projection sources are excluded because they have no as-published trade chart.
Old index-math JSON is rejected by the renderer using view/model provenance,
so a cached translated artifact cannot appear under the new Indexed heading.
All successful arithmetic reports remain warn/unverified pending actual chart
wiring. No chart value, fixture, threshold or methodology decision changed.

Validation:

- `python3 -m unittest tests.test_indexed_monitor_math tests.test_dashboard_scale_agreement tests.test_razzball_monitor_coverage tests.test_methodology_consistency tests.test_vorp_translation_checkpoint`:29 tests,exit0.
- Python syntax checks of the three changed builders/sync script:exit0.
- Native-only builder and sync:exit0; monitor HTML and index report regenerated.
- Playwright Chrome against local dist: five view headers/descriptions visible;
  four publisher cards warn;0/4 rendered verified,4 pending. Replacing the
  report with the legacy main JSON shows a rebuild error and zero source cards.
- `make validate`:exit2 at existing lock-revert rendered test. Main JEG-210's
  source guard expects adjusted curves despite publisher-only Indexed mode;
  changing scoring throws defaultGroupedSources. Logged to JEG-210; not hidden.
- Upstream sync source contained one NUL byte in a comment after JEG-206.
  `py_compile` reproduced ValueError; removal restores loading without logic
  change. Included because the monitor sync path could not otherwise run.
- Local monitor console also reports pre-existing missing fallback JSON paths
  and absent e2e-fidelity artifact. Reviewed sections render; this is not
  production verification or a green verdict for the whole dashboard.

Independent Claude Code MCP review reran12 targeted tests, accepted view/native
separation and missing/zero handling. Its pending-count clarity observation was
addressed. Remaining chart migration belongs to JEG-180/182/209/210, and extra
lineage columns to JEG-207. Roman reviews/merges and verifies production before
Done. No merge/deployment performed by this lane.
