## 2026-10-08 - Freshness lane: producers and stale warnings (fix/freshness-producers)

Rows: GAP-031, GAP-033, GAP-044, GAP-LIVE-SCRAPE-STALE, GAP-E2E-FIDELITY,
GAP-038, GAP-014. No value math touched; no chart numbers can move (the only
`make sync` change is the reference-freshness date basis), so the 12-combo
sweep was not run.

### Changes
- **GAP-LIVE-SCRAPE-STALE:** retired the rebuild chain's Stage 10 (lineage
  rebuild). Evidence it could never work in CI: `build_source_value_lineage.py`
  reads `data/raw/sources/*/2026-09-29` + `week-4` snapshots (gitignored) and
  raises in `require_snapshot_natives()`; `scrape_live_source_pages.py` is
  hard-wired to the Week 4 article URLs; the chain's commit step never adds
  `source-value-lineage.json`. Scheduling the scraper would have refreshed a
  timestamp on Week 4 pages and still failed. The dashboard lineage card now
  shows a "Stale audit" note past 48h; the deploy-time builder step is
  unchanged (it stamps the staleness badge).
- **GAP-E2E-FIDELITY / GAP-031:** `pages.yml` and `preview.yml` run
  `build_e2e_fidelity.py` and `check_data_accuracy.py` after `make validate`
  (continue-on-error: warnings, never deploy blocks). Seed copies committed;
  surfaces entries required, 36h max age. `ir_cross_check` renamed
  `espn_ineligible_cross_check` (ESPN's flag does not say IR); dropped the
  `/home/hatch/...` CSV candidate.
- **GAP-033:** `check_reference_freshness.py` emits `summary.expired_keys`;
  `modules/status.html` supports a surface `warn_path` (dotted, list) that turns
  the surface degraded and names entries. `make sync` dates the report in UTC.
- **GAP-044:** rebuild chain step "Check input lineage (warning only)" runs
  `check_input_lineage.py` after a successful rebuild and commits
  `dist/modules/input-lineage.json`; status surface `input-lineage` warns on
  `mismatches`. Placeholder committed with `generated_at: null`.
- **GAP-038:** `live.mjs` renders root (all five v2 tabs), `/v2/`, `/classic/`,
  and the 404 page; workflow also accepts the last successful Pages deploy's
  commit tag (bot commits that do not deploy). Migration file
  `supabase/migrations/20261008_live_page_synthetic_schedule.sql` (daily 12:15
  UTC, active) - NOT applied.
- **GAP-014:** import-health doc sections marked normative/informative, run
  locations corrected; `tests/test_import_health_schema_doc.py`.

### Verified (check named)
- `make sync` + `CHROMIUM_PATH=... make validate`: exit 0.
- `tests.test_live_page_synthetic` (5 rendered): real dist passes; hidden tab,
  emptied values table, wrong /classic/ tag, foreign 404 each fail. The
  /classic/ and 404 cases pass on origin/main's live.mjs (negative run).
- `node tests/rendered_gate/live.mjs` against production
  (tv-20261008-0505-dac0ff2): root, 5 tabs, /v2/, /classic/, 404 all pass.
- `tests.test_lineage_stage_retired`: fails on origin/main's chain.
- `tests.test_status_warnings` (7): status page degrades on warnings
  (negative: pre-fix page shows working); lineage stale note (negative: pre-fix
  dashboard shows none).
- `tests.test_import_health_schema_doc`: origin/main's doc fails only on the
  blanket-normative marker.
- Supabase read-only: `live-page-synthetic-live` active=false;
  `monitoring.check_observations` has 0 `live_page_synthetic` rows;
  `rebuild-chain-live` schedule `17 */6 * * *`.
- `gh run list` pages.yml last success headSha dac0ff2 -> tag
  tv-20261008-0505-dac0ff2 (matches live).

### Claimed, not confirmed
- The deploy steps produce fresh `e2e-fidelity.json` / `data-accuracy.json` in
  production (needs a post-merge deploy).
- The chain's input-lineage step produces correct results: only CI has the
  run's fresh legs. A local run showed 7 mismatches that are artefacts of the
  stale committed legs, which is why no local result was committed.
- The preview manifest same-bytes compare: the two new deploy steps write
  time-stamped files after validate, like the existing lineage step already
  did; nobody runs `dist_manifest.py compare` in CI today.

### Not mine, noticed
- `tests/test_lineage_freshness.py` has 2 failures on origin/main
  (`test_served_lineage_not_older_than_fixture`,
  `test_usatoday_jsn_lamb_matches_fixture`); not in any Makefile target.
