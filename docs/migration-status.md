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

## Tests Passed/Failed

- Passed: `python3 -m unittest discover -s tests` (`6` tests).
- Passed: HTTP checks for `/` and `/assets/comparison-sources-data.json` return `200`.
- Passed: Playwright MCP desktop render snapshot.
- Passed: Playwright MCP position-filter click smoke test (`QB` to `RB`).
- Not completed: mobile viewport screenshot. Browser resize/select tools are approval-gated in this session.
- Not completed: Playwright CLI/browser direct launch. Local npm/browser cache and headless launch paths failed, but Playwright MCP worked for page verification.

## Known Discrepancies

- The handoff identifies a live public-copy issue: `FantasyPros` is displayed where the standing product rule requires `ECR`.
- The handoff identifies documentation drift in older cron/runbook material.
- The handoff says missing values are null. The exported implementation sometimes omits missing optional fields instead of storing explicit JSON `null`; the frontend treats both `undefined` and `null` as missing and does not zero-fill them.

## Blockers

- `.git` creation in this workspace is currently blocked by filesystem permissions, so normal Git commands require `git --git-dir=.gitstore --work-tree=.` for now.
- Full source pipeline scripts are not included in the ZIP, only static app files and selected finished artifacts.

## Next Highest-Leverage Step

Run the local static dashboard and browser-check that the chart and comparison table render against the imported fixtures.
