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
