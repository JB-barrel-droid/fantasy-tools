## 2026-11-03 - Connector Compare even band (JEG-1412)

Contract: port Jeremy's settled JEG-1125 rule, max(1 point, 3% of the average side), to default `compare_trade` and its guidance. Branch `be/JEG-1412-connector-even-band`, based on `040474c552a324921bdc7f71008ab6da3f823629`. No merge or deployment authorized in this session.

### Verified (check named)

- Ownership: Linear JEG-1412 had no comments or linked PR, was Todo, and no remote JEG-1412 branch existed. Current In Progress tickets showed no writer on this compare path. Related `tools.ts` drafts #1219 and #1252 were parked, with no activity in the preceding four hours; neither branch was touched. Claimed the existing ticket before creating this branch. The managed-agent `claude-lock.json` stores retired resource IDs, not an active code lock. Shared `get_agent_context` returned Tool not found; Personal Context returned unavailable.
- Failing first: `python3 -m unittest tests.test_connector_even_band` against unchanged `tools.ts` failed because the exact floor boundary, 10 versus 11, was classified as roughly even. The site classifies that boundary as decisive.
- `npm_config_cache=/tmp/jeg1412-npm-cache python3 -m unittest tests.test_connector_even_band tests.test_mcp_remote tests.test_trade_bands`: 12 methods passed. The new harness checks 120 combinations (ten sentinels, three scorings, both trade directions, loaded site module and standalone fallback), including percentage and floor boundaries, a gap above two inside the percentage band, real zero, and rounding the side sum before classification. A mutation restoring premature sum rounding is rejected at the outside-before/inside-after sentinel. The test also pins fallback constants to the site's exports and proves the loaded `evenBand` is called. Existing test assertions are unchanged.
- Runtime: default Compare calls the loaded site's `trade.evenBand` when available. Standalone callers use parity-guarded constants. Classification uses side sums before display rounding; structured totals and difference retain one decimal. No get-values API or player-price change. Both text surfaces describe the same band; the unconnected fixed-five-point guidance is removed. The existing general `rule of thumb` qualifier remains in guidance, preserving its assertion.
- Regression is included in `Makefile`'s `test-unit-modules` target. No duplicated broad audit or live endpoint sweep was run.

- `CHROMIUM_PATH=/usr/bin/chromium npm_config_cache=/tmp/jeg1412-npm-cache make validate`: PASS, exit 0 recovered from the original shell's zombie exit status after the environment restart lost the tool handle. The same original run reached the final integration check (`tests.test_writer_audit_enforcement`, 16 passed); its log has no failure or skip summaries. The strict reference comparison reports **agree**, **1,234,507 values compared**, no disagreeing sources, no composite disagreements and no page errors. Full local log: `/workspace/jeg1412-validate.log`. No duplicate broad run was started after the restart. The initial setup-only attempt stopped at sync because Playwright's default browser was absent; the proper run selected installed Chromium. npm cache was redirected to `/tmp` because the default home cache was unwritable.

### Before / after on saved USO roster pairs

These are **historical modeled examples**, not today's live prices or acceptance predictions. Names and player keys are from the saved USO rosters (Yahoo, fetched 2026-10-29); prices are the fixture's archived `baseline_no_league.ddf_value`, rounded to one decimal exactly as the default get-values response. That baseline uses generic 12-team Half PPR values, not USO's custom lineup calculation. Source: `tests/fixtures/league_levels/uso.json`, `provenance` and `baseline_no_league.engine` (`#1077`, `217958ce`). Team 2 is the saved user's team. No current league fetch was made.

| Team A gives | Team B gives | A total | B total | Gap | Shared band | Old connector | New connector |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| Josh Allen | Breece Hall | 33.9 | 32.4 | 1.5 | 1.000 | roughly even | Team B ahead by 1.5 |
| Josh Allen | Parker Washington | 33.9 | 32.4 | 1.5 | 1.000 | roughly even | Team B ahead by 1.5 |
| Josh Allen | Justin Jefferson | 33.9 | 35.7 | 1.8 | 1.044 | roughly even | Team A ahead by 1.8 |

Reproduction: read those players' keys from `league.teams`, round their archived values to one decimal, and compare `abs(A-B) < 2` with `abs(A-B) < max(1, .03*(A+B)/2)`. All other inputs are identical. The synthetic regression additionally pins the opposite change: 100 versus 102.9 becomes roughly even under the percentage band (3.0435), where the old two-point rule was decisive.

### Claimed, not confirmed

- Full live site/connector parity is **not** established: JEG-1409's distinct upstream rounding defect remains. get-values rounds each player's `value` before default Compare receives it, while site and `by_source` use unrounded series. This PR fixes the even-band rule and premature side-sum rounding, not that separate API/data-path issue.
- Cloud CLI GitHub authentication stopped working during the session (`gh api` HTTP 401 and authenticated git read rejected). Environment status still reported its injected credential ready. The connected GitHub app saved the source commit `761c072cbf8867850b33daa0a5ed13989a4e6262`; its tree SHA matches `git write-tree` exactly.
- Automatic approval review rejected the Linear heartbeat as disclosure of repository, credential-failure and validation details to an unverified SaaS destination. That comment was not posted, and no retry was made. Explicit approval for a minimal PR-link/test-result update is pending.
- Automatic approval review also rejected the GitHub tree upload for the strengthened fixtures, mutation test and updated receipt, stating the repository was unverified and the remote write lacked explicit authorization. The upload was denied before a tree or commit was created; no retry occurred. Remote branch remains at `761c072cbf8867850b33daa0a5ed13989a4e6262` (initial implementation and 108-case regression). The improved 120-case regression, mutation test and current receipt are local. Approval for that branch update and a draft PR is pending. No PR exists yet.
- Independent high-risk Claude review and green current-head CI remain required. `mcp` deployment requires Jeremy's separate specific approval. Nothing merged, no Supabase deployment or production-data mutation, and no access change.
