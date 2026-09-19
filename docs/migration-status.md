# Migration Status

Last updated: 2026-09-19.

## What Now Works

- Handoff PDF was found and extracted locally for inspection.
- A persistent Git metadata workaround exists at `.gitstore/` because normal `.git` creation is blocked in this workspace.
- Muse ZIP export was found and extracted into ignored `tmp/` for inspection.
- Active static dashboard files were imported into `app/trade-value-chart/`.
- Current finished data fixtures were imported into `data/fixtures/current/`.
- The inline `players-data` blob in `index.html` matches exported `players.json`.
- Local static server works at `http://localhost:8000`.
- Browser snapshot verification confirms the local dashboard renders the validated chart, eight source entries, comparison tab, source-health header, and build stamp.
- Browser click smoke test confirms the position filter can switch from QB to RB and updates context/boundary ranks.
- A private Sites project has been created and deployed for a hosted Codex/ChatGPT preview artifact:
  `https://trade-value-dashboard-preview.jeremyburstyn.chatgpt.site`
- Private Sites version 2 is deployed from commit `341169284b4fd12cf715b8c2cd0570942015116a`.
- The chart now preserves fixed-pie display semantics in the exported frontend:
  source totals are checked against baked `index_total` metadata, ESPN no longer gets filtered after reindexing, and roster boundary markers show the two transitions from Starter-to-Bench and Bench-to-Waiver.
- The player comparison table now supports configurable metadata/source fields, sorting on visible fields, expandable player rows, and a schema-ready latest-news section.
- The curve widget now defaults to All positions with bottom-up ESPN indexed values plus the three adjusted source projects active; direct published third-party charts are available but off by default.
- The curve widget has a separate Pure VORP basis, currently ESPN-only, computed as ESPN PPG above a positional waiver baseline.
- Mobile tooltip positioning now clamps against the browser visual viewport so touch/hold popups stay on screen.
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

## Tests Passed/Failed

- Passed: `python3 -m unittest discover -s tests` (`13` tests).
- Passed: HTTP checks for `/` and `/assets/comparison-sources-data.json` return `200`.
- Passed: Playwright MCP desktop render snapshot.
- Passed: Playwright MCP position-filter click smoke test (`QB` to `RB`).
- Passed: Playwright MCP fixed-pie/zero-boundary snapshot confirms the default QB view renders `Bench → Waiver after rank 33`.
- Passed: Playwright MCP local render check confirms the default chart starts on All positions, grouped source toggles render, and only ESPN plus adjusted curves are active by default.
- Passed: Playwright MCP local render check confirms Pure VORP mode renders `ESPN pure VORP`.
- Not completed: mobile viewport screenshot. Browser resize/select tools are approval-gated in this session.
- Not completed: Playwright CLI/browser direct launch. Local npm/browser cache and headless launch paths failed, but Playwright MCP worked for page verification.
- Expected: unauthenticated HTTP/browser checks against the private Sites URL return `401 Sign in required`.

## Known Discrepancies

- The handoff identifies a live public-copy issue: `FantasyPros` is displayed where the standing product rule requires `ECR`.
- The handoff identifies documentation drift in older cron/runbook material.
- The handoff says missing values are null. The exported implementation sometimes omits missing optional fields instead of storing explicit JSON `null`; the frontend treats both `undefined` and `null` as missing and does not zero-fill them.
- The exported frontend had an ESPN allowlist filter that removed values after fixed-pie reindexing, causing plotted ESPN totals to drift from baked `index_total` metadata. The frontend now uses the baked ESPN values directly so the chart/table match the fixed-pie artifact.

## Blockers

- `.git` creation in this workspace is currently blocked by filesystem permissions, so normal Git commands require `git --git-dir=.gitstore --work-tree=.` for now.
- Full source pipeline scripts are not included in the ZIP, only static app files and selected finished artifacts.

## Next Highest-Leverage Step

Review the private hosted Sites preview, then continue equivalence testing against Muse.
