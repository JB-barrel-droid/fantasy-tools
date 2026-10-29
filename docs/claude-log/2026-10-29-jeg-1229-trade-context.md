# JEG-1229: shared trade preferences and immutable TradeContext

Branch `claude/JEG-1229-trade-context`, based on main `bf0cfee`. Claude (thread lane), 2026-10-29 UTC.

## Scope

New pure module `app/v2/trade-context.js` (`TradeValueTradeContext`, UMD) and its contract fixture. No edits to
`finder.js`, `league.js`, `v2.js`, `trade.js`, `overrides.js`, MCP or Supabase. Not yet loaded by the page
(`pipelines/build_v2_page.py` is unchanged): route wiring is a later, serialized step after JEG-1219 lands.

Jeremy's 5A (JEG-1220): common preferences shared across the three trade pages, page-specific controls separate.

- **Common:** league settings via `DDFState.normalize` / `decodeQuery` (the same codec as every share link and the
  page's `leagueQuery()`), value basis and player overrides as `overrides.js` holds them (`snapshotContext()`), and source
  availability (available / unavailable / held / unknown).
- **Precedence:** `resolveCommon({link, local, saved})`, section by section. A complete link value context
  (`valuecontext=1`) replays an explicit default; an older link replaces only what it carries. As `applyLinkLeague`: a
  link without `teams` keeps the reader's count and an omitted roster slot keeps the reader's. Availability is always
  the reader's own page.
- **Teams:** `savedTeam(ws, id)` by stable ID (rename keeps the ID; a deleted ID is `missing: true`, never a name
  fallback). `rosterTeam(entries, "local" | "link")` for pasted or linked rosters, with no saved ID.
  `workingTeam(ws, id, entries, provenance?, name?)` for the pair finder's shown roster (`getMine()` / `getTheirs()`):
  the shown snapshot is authoritative and the ID is origin metadata only (`missing`, `matchesSaved`); it never reloads
  the saved roster over an edited, emptied, deleted-origin or foreign-workspace copy (JEG-1219 handshake on #1086).
  Provenance defaults to `saved` only while the copy still matches its saved team, else `local`.
- **Context:** `createContext` / `fromPair` / `fromLeague` / `fromCompare` return deep-frozen contexts. `selectTeam` and
  `withChanges` return new contexts and never touch the workspace or its star. `beginVisit(...).cancel()` returns the
  previous context. `maySave` is false for link and local parts.
- **Route controls:** pair = `normalizeFinderSettings`; league = `ui.maxSize || 2`, keep flags fixed on, rank basis,
  hide force, filters (legacy `naturalValue` reads as `naturalMarket`); Compare = none (discovery controls are dropped
  with a warning).
- **Cache keys:** `cacheKey(ctx, "discovery" | "readout")`, key-sorted and order-insensitive. Names and provenance are
  excluded; league, valuation, availability, roster keys, and either the route controls (discovery) or the deal
  (readout) are included.

## Route discrepancies recorded, not unified (`ROUTE_DISCREPANCIES`)

1. Package size stored twice: `ui.finderSettings.maxSize` (1 to 4) and `ui.maxSize` (2 to 4); both default 2.
2. Keep-starters ticks: reader choices on the pair finder, always on in the league finder.
3. Guardrails (protected positions, backups, lineup minimums): pair finder only.
4. Opponent default: Compare picks the first other saved team with players; the pair finder (JEG-1219) picks none.
5. Ranking basis: league finder only.

Finding, not fixed here: a saved league opponent filter naming a deleted team keeps filtering by that ID in
`opportunities.filterRows`, while the select shows "All opponents". `fromLeague` reports it as a warning.

## Commands and results

```
node tests/node/trade_context_check.cjs                 # 18 passed, 0 failed
python3 -m unittest tests.test_jeg1229_trade_context     # OK (wired in test-unit-modules)
```

Failing before: with the module removed, the check exits with `Cannot find module .../app/v2/trade-context.js` and the
unittest fails. Mutation check (eleven single-line breaks of the module: no freeze, team name in the key, complete link
ignoring the default, deleted ID falling back to another team, controls left out of the discovery key, link-supplied
availability, league keep flags read from ui, roster order in the key, a key on both deal sides, an origin ID beating the shown roster, a saved name on an edited copy): each one fails at
least one case.

Related suites on this branch: `tests.test_validate_shards`, `tests.test_render_sweep_shards`,
`tests.test_jeg1216_lineup`, `tests.test_v2_league_units`, `tests.test_v2_copy_names`, `tests.test_launch_copy_guard`
pass. `tests.test_render_sweep_coverage` has the same 4 failures on main `bf0cfee` without this change (three unwired
render modules); not touched here.

`dealPartner(ctx)`: on the league finder a readout uses the one opponent holding every received key, so the same
explicit trade has the same readout key on all three routes (asserted in the fixture).

## Next (not in this PR)

Route wiring after JEG-1219's reviewed head lands, serialized by Codex: register the script in `build_v2_page.py`,
then narrow adapter hunks in finder.js (JEG-1219 owner), league.js and v2.js. JEG-1230's readout adapter can key its
cache on `cacheKey(ctx, "readout")`.

## JEG-1259: corrections and carrying one trade between pages (same lane, same branch)

Main merged normally (`b863069`, includes #1072's uncapped search and #1094's saved-team picker). #1110's journey
contract (`node tests/node/uso_site_journey_contract.cjs check app/v2 .../league.json`) passes 9 of 9 on this tree;
before the merge its discovery check found 10 of 325.

Reviewed blockers fixed:

1. `maySave`: with no `commonProvenance`, the context's own provenance decides, so a link or local visit can never save
   its league, basis or overrides (Codex's exact reproduction pinned).
2. Discovery cache keys keep each team's stable ID with its roster; readout keys stay identity-free. Swapping the
   rosters of tB and tC under opponent filter tB now changes the key; a rename does not.

New immutable context fields: `workspaceId`, `pricing` (`{mode: "league" | "modeled", levels: {ddf, market} |
{modeled}, rostered, reserve}`; each level is `levelIdentity(level, {rows, allocation, weights, keys})`, a hash of every
value of every player the trade touches plus the level's allocation and weights), `versions` (settings, basis with
overrides, sources, pricing) and `origin` (route, workspace, origin team IDs, partner IDs). Sources keep the page's own
`version` label. Pricing is part of every cache key.

Transfer: `toTransfer(ctx)` → `encodeTransfer` (base64url JSON with a checksum) → `decodeTransfer` → `receive(transfer,
here)`. `here` is the receiving route, its resolved common (carried settings applied as a complete link), its own
identity of the same level(s) run with the carried rostered set, and its workspace. Result: `{status: "ok", context}`
with the carried rosters (origin IDs kept on the same workspace, ID-less link rosters on any other), or `{status:
"hold", reasons}` with codes `settings-changed`, `basis-changed`, `overrides-changed`, `sources-changed`,
`level-missing`, `level-changed`, `rows-changed`, `allocation-changed`, `weights-changed`, `team-missing`,
`package-missing`, `context-missing`, `context-unreadable`, `context-unsupported`. A hold has no context, so nothing is
repriced on another level. Nothing writes the workspace. No freshness duration: "stale" means a different version or
row identity, never an age.

Commands (head after this commit):

```
node tests/node/trade_context_check.cjs                       # 27 passed, 0 failed (journey case SKIPs without #1110's file)
JOURNEY_CONTRACT=<#1110 tests/node/uso_site_journey_contract.cjs> node tests/node/trade_context_check.cjs   # 27 passed, 0 failed
python3 -m unittest tests.test_jeg1229_trade_context           # OK
```

Failing before: the same test file against the module at `8c677a2` gives 18 passed, 9 failed (both reviewed blockers,
the context-loss fixture, both goldens, reload/share, holds, level in keys, journey diff). Goldens are hand-checked
(Alpha's starters 109 → 113 at the ddf level for 102 ↔ 204). Mutations: 22 single-line breaks (the eleven above plus
maySave fallback, discovery IDs stripped, transfer dropping basis, transfer dropping level, receive ignoring level mode,
rebuilt rows, sources, checksum, substituting the reader's saved team, level out of the cache key, a missing row read
as empty); each fails at least one case.

Route integration (not in this commit): league.js builds `pricing` from #1105's `getLeagueLevel` at both levels and
puts `encodeTransfer(toTransfer(ctx))` on "Open in Compare a trade"; Compare and the pair finder run the same levels
with the carried `rostered` set and call `receive`, showing the hold's reason instead of modeled numbers. Those hunks
belong to the league.js / v2.js / finder.js owners (#1105 / JEG-1249, JEG-1219) and are serialized by Codex.
