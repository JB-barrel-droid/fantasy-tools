## 2026-11-03 - JEG-1321 isolated discovery-options adapter

Contract: prepare a pure adapter and tests while preserving PR #1084 ownership
of league.js. Parent explicitly forbids edits to league.js, opportunities.js and
trade-context.js until ownership is resolved. Branch:
`fe/JEG-1321-discovery-options`, based on main `efc39d4d`.

### Verified (check named)

- JEG-1321 claim comment `193ce84f-bb5f-4fe7-83c1-aa3f20682fb4` and In Progress
  update succeeded after Jeremy's standing approval was supplied by the parent.
- `python -m unittest tests.test_jeg1320_discovery_controls tests.test_jeg1321_league_discovery_options -v`:
  both tests pass. The new runner checks seven cases, including shared settings
  precedence, 1-for-1, keep flags, all guardrail fields, browser export and purity.
- The new runner on frozen USO fixture data, using the existing league pricing
  helpers: 11 opponents, 3,188 identical default rows (IDs, order, edge and chart
  results compared with current opportunities.computePairing); protect RB drops
  1,822 candidates. Each retained trade independently preserves RB starter value.
- Synthetic default parity compares the entire findTrades result. An in-memory
  mutation removing the adapter's guardrails fails the protected-RB regression
  (`guardrailDropped > 0`) and two additional adapter checks; no source mutation.
- `git diff --check` passes. No fixture, value-math, shared-path or asset-loader
  edits; no broad suite, merge, deployment or live verification.
- `linear.get_agent_context` could not supply notes: server returned
  `Tool get_agent_context not found`.

### Later integration patch (not applied)

1. Load discovery-controls.js and league-discovery-options.js before the league
   consumer, and copy the new adapter in build_v2_page.py's asset list. Obtain
   ownership of those loader/build paths first; this preparatory PR does not
   change browser execution.
2. In league.js, read `D.fromWorkspace(ws.ui)` once for each search. Feed its
   search fields through to the pairing context. Offer sizes from `D.SIZES`,
   including 1, and persist keep flags/guardrails via the shared record. Preserve
   #1084's `result.pricingRows` snapshot at the completion of each search.
3. In opportunities.js pairingSteps, replace the existing findTrades options
   literal with `A.finderOptions(record, ctx, mineRows, theirRows)`. The adapter
   uses the existing `D.searchOf(record)` defaults and passes full roster/shape
   context exactly as the pair finder does. Keep the complete candidate list.
4. Resolve cache context before wiring: current trade-context.js routeControls
   for league forces both keep flags true, permits sizes 2-4, and drops guardrails.
   Simply calling cacheKey(fromLeague(...), "discovery") cannot distinguish the
   new controls. Extend the normalized league control contract under explicit
   ownership, then key pairing/result caches on that genuine TradeContext plus
   the existing exact pricing inputs. Test each control invalidates results.
   Remove resolved discrepancy entries only once both routes agree.
5. Resolve migration under workspace ownership: toUiPatch omits legacy maxSize,
   setUi merges it, and normalizeWorkspace supplies/retains it. Deleting it in a
   transient adapter output does not satisfy persistence cleanup. Preserve D3 A:
   finderSettings.maxSize wins; finish a save/reload regression at the owning
   storage boundary rather than changing defaults here.
6. After ownership is clear and wiring is complete, run page controls/cache/
   persistence regressions and the required serial validate/render gate once.
   Existing JEG-1320 source-text tests explicitly pin legacy league call/menu
   behavior; their owning integration must replace those historical assertions
   with behavioral default-parity checks under the ticket's approved new rule.

### Claimed, not confirmed

- JEG-1321 is not complete: this adapter is intentionally unreferenced by the
  site. User-facing controls, stale-cache prevention, migration cleanup, full
  page row/readout parity and live behavior await the integration owner.
- Global session/registered-lock state was unavailable to this cloud lane.
  Only these newly claimed adapter/test/log paths were edited.
