# Migration Status

Last updated: 2026-09-20.

## What Now Works

- Handoff PDF was found and extracted locally for inspection.
- ~~A persistent Git metadata workaround exists at `.gitstore/`.~~ Resolved: the repo has normal `.git` metadata and a GitHub remote; use plain `git` commands.
- Muse ZIP export was found and extracted into ignored `tmp/` for inspection.
- Active static dashboard files were imported into `app/trade-value-chart/`.
- Current finished data fixtures were imported into `data/fixtures/current/`.
- The inline `players-data` blob in `index.html` matches exported `players.json`.
- Local static server works at `http://localhost:8000`.
- Browser snapshot verification previously confirmed the local dashboard renders the validated chart, source entries, comparison table, source-health header, and build stamp.
- Browser click smoke test confirms the position filter can switch from QB to RB and updates context/boundary ranks.
- A private Sites project has been created and deployed for a hosted Codex/ChatGPT preview artifact:
  `https://trade-value-dashboard-preview.jeremyburstyn.chatgpt.site`
- Private Sites version 2 is deployed from commit `341169284b4fd12cf715b8c2cd0570942015116a`.
- The chart now preserves fixed-pie display semantics in the exported frontend:
  source totals are checked against baked `index_total` metadata, ESPN no longer gets filtered after reindexing, and roster boundary markers show the two transitions from Starter-to-Bench and Bench-to-Waiver.
- The player comparison table now supports configurable metadata/source fields, sorting on visible fields, expandable player rows, and a schema-ready latest-news section.
- The curve widget now defaults to All positions with ESPN live indexed values plus four adjusted source projects active; direct published third-party charts are available but off by default.
- Pure VORP is now an optional ESPN-only source curve on the same chart screen rather than a separate basis.
- The chart now has selectable Y-axis value bands, so the same player order can be inspected at full, elite, starter, or bench-value scales.
- League roster shape is adjustable in the chart: QB/RB/WR/TE/FLEX/bench counts redistribute each source's fixed-pie values by position and move Starter/Bench/Waiver markers accordingly.
- K/DST controls are present but fail closed until an ESPN projection-derived K/DST artifact exists; the removed preseason FantasyPros projection wiring is not used as a substitute.
- Mobile tooltip positioning now clamps against the browser visual viewport so touch/hold popups stay on screen.
- Mobile/touch tooltip state now clears on release/cancel and keeps a vertical crosshair while pressed.
- All positions now defaults to one mixed overall value curve order, locked to ESPN value, instead of positional preseason chunks.
- The chart Y-axis now rescales to the currently visible zoom window as the X-axis slider changes.
- League settings are now inside the curve widget and source toggles gray out when the current scoring/team setting is not available in the artifact.
- Lock player order is the single order selector shared by the chart and bottom table.
- The bottom player table remains a real horizontally scrollable table on vertical phones.
- A collapsible Players in view table below the graph lists visible players and active source scores for the current zoom window.
- A CBS Adjusted curve is derived in the frontend from CBS plus the current adjustment ratios, then fixed-pie rescaled. This is labeled as an interim derived curve until an upstream adjusted CBS artifact is produced.
- A read-only freshness audit pipeline exists at `pipelines/check_reference_freshness.py`.
- Initial discovery docs exist:
  - `docs/architecture-current.md`
  - `docs/migration-plan.md`
  - `docs/dependency-map.md`
  - `docs/risk-register.md`
- Repository baseline files exist:
  - `.gitignore`
  - `.env.example`
  - `README.md`

## What Remains Muse-Dependent

- Live public dashboard.
- All upstream calculation/build scripts.
- All source collectors and authenticated FantasyPros browser automation.
- Current publish pipeline and render gates.

## What Changed

- No production systems were touched.
- No Supabase reads or writes were performed.
- No scrapers were run.
- No app redesign was attempted.
- Local documentation was created from the handoff PDF.
- Static dashboard source and current data fixtures were imported from the Muse ZIP.
- Initial dependency-free regression tests were added under `tests/`.
- User feedback captured: the chart is intended to compare fixed-pie indexed trade-value charts, with source totals matching the same value-pie logic and roster lines showing Starter-to-Bench and Bench-to-Waiver transitions.
- Fixed-pie diagnostics were added to the frontend and exposed as `window.TradeValueCurveDiagnostics`.
- User clarified that DDF/projection-derived values are outdated in-season; they should be treated as legacy/stale context unless refreshed and revalidated, not as the current source of truth.
- The stale ESPN post-index allowlist filter was removed from both chart and comparison views so displayed values match the fixed-pie artifact totals.
- Boundary labels were changed from three rank labels to the two intended roster transition lines.
- Added an empty `player-news.json` artifact so news can be connected later without changing the table UI contract.
- Reorganized source-curve controls into Bottom-up indexed, Adjusted source projects, Direct published charts, and Pure VORP groups.
- Removed dashboard-facing DDF labels, replacing them with legacy/house-model wording where the old projection output is still referenced.
- Neutralized adjusted-source copy from "poor math" to shifting weight toward our view of value, with an info popover explaining common adjustments.
- Added graph zoom presets for Starter, Bench, and Waiver zones.
- Fixed Hide zero-value tail and Bench-to-Waiver marker logic to use ESPN pure VORP as the zero-value boundary rather than all visible source families.
- Added chart controls for roster shape and Y-axis value bands. Roster-shape changes redistribute source values by position without modifying source artifacts or production data.
- Updated expanded player rows in the bottom table to show player-value news only. News entries are filtered for fantasy/value relevance and labeled as fresher or older than the model values when timestamps are available.
- Added a reference-freshness report flow. For 2026-09-20, the checked references are not same-day: seven known dates are stale, one date is unknown, and all eight tracked reference values were unchanged from the prior run.

## Tests Passed/Failed

- Passed: `python3 -m unittest discover -s tests` (`14` tests).
- Passed: `python3 -m pytest -q` (`14` tests).
- Passed: `node --check app/trade-value-chart/assets/curve-widget.js`.
- Passed: `node --check app/trade-value-chart/assets/comparison-dashboard.js`.
- Passed: `node --check dist/assets/curve-widget.js`.
- Passed: `node --check dist/assets/comparison-dashboard.js`.
- Passed: `python3 pipelines/check_reference_freshness.py --today 2026-09-20`.
- Passed: HTTP checks for `/` and `/assets/comparison-sources-data.json` return `200`.
- Passed: Playwright MCP desktop render snapshot.
- Passed: Playwright MCP position-filter click smoke test (`QB` to `RB`).
- Passed: Playwright MCP fixed-pie/zero-boundary snapshot confirms the default QB view renders `Bench → Waiver after rank 33`.
- Passed: Playwright MCP local render check confirms the updated page loads without console errors.
- Passed: Playwright MCP local render check confirms the default chart starts on All positions, grouped source toggles render, and ESPN plus adjusted curves are active by default.
- Passed: Playwright MCP local render check confirms Pure VORP mode renders `ESPN pure VORP`.
- Passed: Playwright MCP local render check confirms the fresh-script preview starts `All positions · fixed-pie indexed values · locked to ESPN value`.
- Not completed: mobile viewport screenshot. Browser resize/select tools are approval-gated in this session.
- Not completed: Playwright CLI/browser direct launch in this latest run. npm/cache setup was moved into writable `tmp/`, but Chromium launch failed under the macOS sandbox with a MachPort permission denial.
- Expected: unauthenticated HTTP/browser checks against the private Sites URL return `401 Sign in required`.

## Known Discrepancies

- The handoff identifies a live public-copy issue: `FantasyPros` is displayed where the standing product rule requires `ECR`.
- The handoff identifies documentation drift in older cron/runbook material.
- The handoff says missing values are null. The exported implementation sometimes omits missing optional fields instead of storing explicit JSON `null`; the frontend treats both `undefined` and `null` as missing and does not zero-fill them.
- The exported frontend had an ESPN allowlist filter that removed values after fixed-pie reindexing, causing plotted ESPN totals to drift from baked `index_total` metadata. The frontend now uses the baked ESPN values directly so the chart/table match the fixed-pie artifact.
- CBS Adjusted is currently frontend-derived rather than artifact-native because the current exported artifact does not contain a real `cbs_adjusted` curve.
- K/DST are present in `players.json`, but this artifact has no ESPN K/DST projection fields. The UI does not fall back to the old FantasyPros/preseason projection path.
- The 2026-09-20 freshness audit shows current artifacts are not same-day fresh: player, ESPN, prediction-market, K/DST, comparison, and news dates remain from 2026-09-16 through 2026-09-19; `news.generated_at` is unknown.

## Blockers

- ~~`.git` creation is blocked, so Git commands require `--git-dir=.gitstore`.~~ Resolved; plain `git` works.
- Full source pipeline scripts are not included in the ZIP, only static app files and selected finished artifacts.

## Next Highest-Leverage Step

Review the private hosted Sites preview, then continue equivalence testing against Muse.
