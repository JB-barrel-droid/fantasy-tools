# JEG-1322: isolated pair-finder listing filters

Preparatory component only. The finder page does not load this module yet;
JEG-1322's controls, workspace persistence and page-level acceptance remain open.

## Ownership and scope

- Branch: `codex/JEG-1322-pair-discovery-filters`, based on main `d4673cd6`.
- Read the full JEG-1322 ticket and comments, JEG-1321 ticket and claim,
  AGENTS.md, HANDOFF.md and `docs/specs/trade-page-parity.md` section 6.2.
  The agent-context lookup returned `Tool get_agent_context not found`;
  code and repository docs supplied context.
- No prior JEG-1322 claim, remote branch or PR found. All 37 open PR file
  lists were checked before the exclusive new-file claim.
- PR #1174 is open and owns `app/v2/finder.js`. JEG-1321 owns the separate
  `league-discovery-options.js` adapter and its tests. Neither path was edited.
- Only four new exclusive paths: the component, its Node contract, its Python
  wrapper and this dated handoff. No build, Makefile, storage, engine, shared
  file, production, merge or deploy changes.

## Component contract

`TradeValuePairDiscoveryFilters.filterGroups(groups, record, fitOf, viableOf)`
is exported for browser and CommonJS use. `record` is the shared normalized
discovery record, not workspace `ui`. The function uses
`TradeValueDiscoveryControls.listingOf` and delegates the fit, hide-force,
minimum-capture and minimum-chart checks to existing
`TradeValueOpportunities.filterRows`. It ignores the saved opponent field:
the pair route already has one partner, and a league-wide opponent selection
must not hide its results.

The callbacks take a group, matching the existing finder helpers:

- `fitOf(group)` returns the existing fit for `group.best`, or null when
  unjudged. No new natural-fit or force-fit predicate is defined here.
- `viableOf(group)` returns the existing viability label, or null. Viable-only
  delegates to `TradeValueFinder.viableGroups`. Without an evaluator it has
  no effect, matching today's finder page when fit context is unavailable.

The output preserves incoming order and original group/package references.
It selects whole groups by their best package without promoting alternatives.
All fits, force and unjudged groups remain with default controls. A missing fit
stays unjudged: hide-force keeps it; natural-only excludes it.

## Verified

`python -m unittest tests.test_jeg1322_pair_discovery_filters -v` passes both
Python tests. Its Node contract passes 14 cases, including 80 combinations
checked against the existing league predicate, browser/CommonJS exports,
frozen input integrity, default identity/order, opponent isolation, thresholds,
and viable-only composition. A real `tradeFit` example yields natural, market
and force labels; the filter consumes those labels without recomputing math.

The second Python test evaluates an isolated in-memory source mutation that
bypasses listing filtering: both the natural-only and hide-force cases fail.
Tracked files are never modified for this discrimination check.

`git diff --check` passes. No full validate, rendered suite or broad suite was
run, per this lane's focused-test scope. These tests are runnable directly;
the Makefile's explicit module list has not been changed, so the new contract
still needs suite registration during integration. No CI result is assumed.

## Integration handoff

After the finder owner releases `finder.js` / PR #1174 and ordering is resolved:

1. Load/copy the component and its shared discovery-controls dependency in
   the page builder; the builder currently does not load discovery-controls.
2. Read the shared record with `DiscoveryControls.fromWorkspace(ws.ui,
   {viableOnly: S.viableOnly})` and mount the agreed fit/hide-force controls.
   Save through the shared record's existing patch API, keeping viable-only
   session-only. Coordinate legacy `ui.maxSize` cleanup with JEG-1321.
3. Pass the page's existing best-package `fitFor` and `viabilityFor` callbacks.
   Apply filtering before core caps and pagination, with consistent counts,
   empty-state copy and show-more behavior. This component does not rank or cap.
4. Register the focused check, then run the coordinated `make validate` and
   finder render acceptance. Confirm default search and displayed results
   match before/after, and fit/hide-force interactions work on the page.

This handoff does not claim user-facing completion or independent review.

## Delivery

Implementation commit `8cfcd9346c63466da5e6d9741c6a58490bdf6730` was pushed
and verified on remote branch `codex/JEG-1322-pair-discovery-filters`.
Automatic approval review rejected `github_create_pull_request` targeting
`datadrivenfootball/fantasy-tools`, head this branch, base `main`, draft true.
Its reason: opening even a draft PR is an external repository commitment,
and the supplied authorization for parallel implementation did not explicitly
authorize PR creation. The action was denied; no PR was created at that time.
It was not retried through another tool.

The coordinator then supplied Jeremy's explicit authorization for DDF ticket
branch pushes and draft PR creation/updates. Before retrying, the remote head
was confirmed as `c87639275bb3fc06de10a219888b17848959a3c6` and the branch's
all-state PR list was empty. One retry of the same creation succeeded:
[draft PR #1300](https://github.com/datadrivenfootball/fantasy-tools/pull/1300).
The approval blocker is resolved. This follow-up changes only the handoff;
the implementation and test results above remain unchanged.

The remaining integration is deliberately deferred under this lane's scope,
not an execution failure. The implementation and focused tests are available
on the remote branch for the coordinator/owner; no merge or deploy occurred.
