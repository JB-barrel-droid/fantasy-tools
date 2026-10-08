## 2026-10-08 - Ops dashboard (feat/ops-dashboard, lane 10)

Contract: one internal dashboard, noindex and unlinked, answering "is everything working and fresh?"
across pipelines, back end, front end and alerts. Consolidate rather than add a fourth page. Read
only data the pipeline publishes. Every block shows its own as-of time and turns amber or red when
stale. Headless test with green, stale and failed fixtures that fails on a broken page.

### What changed

- `modules/status.html` is replaced in place (same URL, still noindex, still unlinked) by the ops
  dashboard. The old published-files table is now its "Published files" card. Cards:
  - **Alerts:** open `ops-alert` issues and the Supabase monitor verdict.
  - **Pipelines:** scheduled jobs (one row per workflow, with every pg_cron slot that dispatches it,
    retry slots included, next run computed from the cron, the last run's outcome and duration, and
    each monitoring check it owns), and per-source ingest (last attempt, last success, content saved,
    rows, review rows, blocked reason).
  - **Back end:** the rebuild chain (outcome, held and failed sources with the reason, promoted
    sections, fit, adjusted sections, post-rebuild validate), the C1-C10 checkpoint matrix, the
    players.json bake (snapshot per source), week history (captured weeks, completeness), the
    Supabase security posture and the identity review queue.
  - **Front end:** deploys (pages.yml runs; the live build tag read from the browser compared with
    main's HEAD and the last successful deploy), the live synthetic check (root, v2 tabs, classic,
    404), published files fetched live (a missing file shows as an asset 404), and the freshness
    labels readers see.
- `pipelines/build_ops_status.py` → `dist/modules/ops-status.json` publishes the facts nothing
  else did: pages runs with head_sha, main HEAD, the live tag, the last live-page-synthetic report
  (the workflow only uploads it as a run artifact; the producer follows the artifact redirect
  without forwarding the GitHub token), open ops-alert issues, the identity queue
  (`public.player_identity_unresolved_v`) and players.json snapshot dates. A block that fails to
  read records `status: "error"` and the reason. It never crashes the step and never reports green.
- `health-artifacts.yml`: one step at the end (`if: always()`, `continue-on-error`). It builds,
  commits and pushes ops-status.json, then dispatches pages.yml. The monitoring lane agreed to this
  placement. The earlier steps are untouched.
- `modules/surfaces.json`: new `ops-status` surface (required, at least 5 blocks, under 7 h).
  Makefile `test-unit` runs `tests.test_ops_dashboard`. The page is documented in SYSTEM_MAP.md
  ("Internal Monitoring"), README.md and docs/MODULES.md.
- Staleness limits: CI feeds go amber after 7 h and red after 25 h (health-artifacts runs every
  6 h, the monitoring lane's change). make sync feeds (freshness, history) go amber after 26 or
  30 h. The synthetic run goes amber after 30 h. The bake goes amber after 36 h.

### Verified (check named)

- `python3 -m unittest tests.test_ops_dashboard`: 7 tests OK. The rendered card states were
  printed and inspected. Green fixture: all 14 cards OK. Stale fixture: chain, ingest and
  synthetic amber, the rest OK. Failed fixture: alerts, monitor, jobs, ingest, chain, deploy,
  synthetic, surfaces and freshness red.
- Negative: the "staleness ignored" broken page is caught by the stale scenario. The "failures not
  propagated" broken page is caught by the stale and failed scenarios. origin/main's status.html
  errors in every scenario.
- `make sync` then `CHROMIUM_PATH=... make validate`: exit 0.
- `tests.test_published_surfaces`, `tests.test_launch_qa_surfaces` (noindex), `tests.test_health_artifacts_summary_step` and
  `tests.test_health_artifacts_publish`: OK. The workflow YAML parses.
- Producer run locally with `GH_TOKEN=$(gh auth token)`. deploy: live tag tv-20261008-0505-dac0ff2 =
  main dac0ff2, verdict current. synthetic: run 37620633018 report read via the artifact. alerts:
  0 open. players_bake: read. identity: error "SUPABASE_URL not set" (expected locally). This run
  is the committed seed.
- Rendered against the real synced dist at 1300 px and at 375 px (phone): no page errors, no
  horizontal page scroll, status pills carry text labels.

### Claimed, not confirmed

- That the CI step's `GITHUB_TOKEN` can read issues. The monitoring lane is adding `issues: write`
  to the workflow permissions. Without it the alerts card shows Unknown with the API error; it does
  not show green.
- The security card reads `monitoring-summary.json` `security`, which comes from the monitoring
  lane's `public.monitoring_security_posture()`. The field names come from that lane's corrected
  message (count fields, a `details` name list, and `{read_error}` shown as Unknown). They have not
  been checked against an applied function. Until it is applied the card is Unknown.
- The synthetic card's per-page table needs the freshness lane's live.mjs `pages[]` (not merged).
  Until then it shows amber, "root build-tag check only".
- `fantasypros_trade_chart_ingest` is not a monitoring check today, so FantasyPros ingest shows
  "no monitoring check records this ingest" (Unknown). This is a true gap, not a page bug.

## 2026-10-08 - Ops dashboard follow-up after merge (fix/ops-dashboard-2)

Integrator asks: verify the port of the freshness lane's warn_path warnings into the new page,
adapt tests/test_status_warnings.py (written for the old page), surface the freshness lane's
other signals, and pick up the monitoring lane's final fields.

### Changed

- **Port verified and kept.** `warningsAt` and `warn_path` in `evaluateSurface` are kept. A
  surface with warnings is now amber and also states its staleness. Before, the warning
  returned early and hid an expired timestamp.
- **New back-end card "Derived checks", one row per check:**
  - `e2e-fidelity.json`: amber after 36 h, red after 74 h; names any source that is not OK.
  - `data-accuracy.json`: amber after 36 h; red on violations or a bad status.
  - `input-lineage.json`: amber after 8 h; amber while sections lag, naming them; Unknown while
    the file has no `generated_at`.
  - `source-value-lineage.json`: "Stale audit" amber after 48 h or when older than the fixture;
    never red, because it is a manual audit by design.
- **Monitoring lane's `producer` block.** The feeds health-artifacts writes (monitoring summary,
  ops status, import health, checkpoints) go amber after cadence + 1 h and red after
  `stale_after_minutes` (12 h, the same value as dashboard.html SYS_STALE_MIN). Past that limit
  the monitor card says the verdict is unknown and shows the last headline only as history.
  The security card already used the final `.security` fields (dac9825).
- **`modules/surfaces.json`.** The import-health, pipeline-checkpoints and monitoring-summary
  surfaces still had a 1 h max age from the 30-minute era. The monitoring lane moved
  health-artifacts to every 6 h, so they would always show amber. They are now 12 h.
- **`tests/test_status_warnings.py`, adapted to the new page with the same intent:**
  - Rows are read from `tr[data-surface]` `data-status` (ok/warn) and the result cell.
  - The negative test cuts the new warnings block and still expects the lagging surface to read OK.
  - `test_reference_freshness_lists_expired_keys` used `players.pm_snapshot` as its stale input.
    The producers lane retired that item (9afaede), so the test now uses `players.espn_snapshot`.
    It still asserts that a stale input is listed in `expired_keys`.

### Verified (check named)

- `tests.test_status_warnings`: 7 OK. On merged main before this branch it was 2 errors and 1
  failure: the old selectors, the old cut anchor, and the retired pm key.
- `tests.test_ops_dashboard`: 7 OK.
  - Stale fixture: the derived card is amber (manual audit 60 h old, one lagging section).
  - Failed fixture: the derived card is red (data-accuracy violation).
  - A 13 h old monitoring summary is red. With the `producer` handling disabled the same test
    fails ('bad' != 'warn'), which proves it checks the producer thresholds.
- `make sync` then `CHROMIUM_PATH=... make validate`: exit 0.
- `tests.test_published_surfaces`, `test_launch_qa_surfaces`, `test_health_artifacts_summary_step`
  and `test_health_artifacts_publish`: OK.
- Rendered against the real synced dist at 375 px: no page errors. The derived card is amber
  because the lineage audit is 5 days old and input-lineage has not been produced yet.

### Claimed, not confirmed

- The input-lineage card stays Unknown until the rebuild chain writes its first
  `input-lineage.json` with a `generated_at` (freshness lane).
