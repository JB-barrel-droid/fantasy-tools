## 2026-11-03 - Isolated Versus Vegas page / JEG-1481 (part of JEG-1195)

Contract: consume the merged offline weekly-input artifact in a separate local
page. Compare weekly ECR and PropLine only, keep missing/partial rows visible
and unflagged, and persist scoring/position/coverage/sort in the URL. No live
route, source fetching, writer, schedule, credentials, Supabase, production data,
pricing, merge or deploy. T2 build, Codex cloud Versus Vegas session.

Source: `origin/main` at `ad0cfc3a40ed3cdbb6d3291e4bb1c735d5bd6dfc`.
Branch: `fe/JEG-1195-versus-vegas`. Ownership checks found no open Versus Vegas
PR, matching remote branch, or active implementation claim. The isolated
worktree was created before the Linear claim; no product edits preceded the
claim. JEG-1481 tracks this bounded child; JEG-1195 remains incomplete.

### Verified (check named)

- `python3 -m unittest tests.test_weekly_inputs_contract tests.test_build_weekly_inputs tests.test_versus_vegas`: 104 tests passed. Includes existing contract/producer regression suites and 11 new adapter/filter tests: pinned sources, fail-closed validation, no ESPN fallback, real zero, missing reasons, partial/unresolved/old rows unflagged, ranks never subtracted from points, empty data, additive-version warnings, safe script payload and CLI output preservation.
- `node --check app/versus-vegas/view.js`: passed. The Python suite executes the pure JS filters, coverage counts, sort and formatting using Node.
- Local CLI build using `tests/fixtures/weekly_inputs/valid/unavailable.json`: wrote `/tmp/jeg1481-preview/index.html`, four synthetic rows. No publication path is wired.
- Shared validator owns validity and freshness. Adapter subtracts only complete current weekly points for resolved identities. It generates descriptive direction only; verified plays stay empty pending shared compute/play gates. No rank-to-points conversion or recommendation threshold was introduced.
- `make validate`: attempted, exited 2 at `sync` because the installed Playwright expected `/home/agent/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell`, which is absent. Later validation targets did not run. Generated outputs from this failed sync were preserved under `/tmp/jeg1481-generated-after-validate`; only this run's tracked generated changes were restored, and its untracked generated files were moved there. No generated output is included in this PR.
- Browser installation attempted with `PLAYWRIGHT_BROWSERS_PATH=/tmp/ddf-versus-browsers python3 -m playwright install chromium-headless-shell`: runtime proxy denied `https://cdn.playwright.dev/builds/cft/151.0.7922.34/linux64/chrome-headless-shell-linux64.zip` with HTTP 403 `Domain forbidden`. No alternate host or proxy bypass attempted. The installer performed its internal retries and exited 1.
- Linear `get_agent_context` returned `McpServerError: Tool get_agent_context not found`; ticket/comments, repository guidance and committed code were read directly.

### Claimed, not confirmed

- Local browser render checks could not launch because Chromium is absent. Two hermetic Playwright tests cover mobile layout, touch targets, all-row visibility, safe text rendering, missing coverage, URL changes/reload/back, comparable filtering and absence of external requests. A dedicated read-only PR workflow runs them and retains a mobile screenshot; CI result is recorded in the ticket/PR after push.
- `make validate` is not green locally. Full repository validation, exact-head CI and independent Claude review remain required before merge. No test or assertion was waived.
- No live data freshness, published page, verified plays or runtime source availability was checked. Existing JEG-1195 source activation and shared compute dependencies remain open; shared live-route integration needs coordination.
