# JEG-1224: shared-link value basis and override loss

Bug and contract packet. Research and QA spec only: no production code, existing test or
active PR branch (#1071, #1072) is changed. Parent: JEG-1220 (normalized context plan).
Cross-tab roster precedence stays with JEG-1114. Public wording stays with JEG-1223.

## Pinned revision and how to rerun

- `main` at `021c5bfd6d631ba6ddfd4347e60d43fab71132b1` (2026-10-29 01:37 UTC), which includes
  the league finder release #1062 (complete value context on finder and league links) and the
  interactive trades release #1069.
- Harness: `tests/jeg-1224/shared_link_regressions.mjs` (Node 22, no network, no build), and its
  negative mutations `tests/jeg-1224/harness_mutations.mjs` (JEG-1254).

```
node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs
node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs --strict
node --experimental-strip-types --no-warnings tests/jeg-1224/harness_mutations.mjs
```

The first command exits 0 when every case matches its recorded state (22 cases: 14 failing
specs, 8 passing guards on the pinned revision). `--strict` exits 1 while any spec fails; it is
the "failing before, passing after" check for the fix. Any harness error (see "Unmet contract
or broken harness" below) exits 2 in every mode and is never counted as a failing spec. The harness loads `app/v2/ddf-state.js`,
`app/v2/overrides.js`, `app/v2/ddf-assist.js` and `supabase/functions/mcp/rpc.ts` read-only,
with stubbed storage, engine and get-values. It is not wired into `make`, so it cannot turn
`make validate` red. When a fix lands, its PR flips the case's `today` to `"pass"` and moves the
case into the regular suite (for example `tests/node/ddf_state_check.cjs` and
`tests/node/mcp_remote_check.mjs`).

Evidence kinds used below: **executed** (run by the harness on the pinned revision),
**source** (read from source at the pinned revision, not executed), **gap** (not checked).

Gaps, disclosed: the live site (github.io) is blocked from this environment, so the served
`v2/ddf-state.js` the MCP function loads at cold start was not compared with main, and nothing
here was run against the live site, the deployed `mcp` function or a real ChatGPT or Claude
client. Page routing in `v2.js` (`readTradeHash`) was read, not executed: it lives inside the
page closure and needs the built site.

## Findings

| ID | Surface | What is lost | Evidence |
| -- | -- | -- | -- |
| C1-C3 | DDFState codec | `basis`, `ov` and `valuecontext` are not fields of the state. `decodeQuery` drops them with no warning; `encodeQuery` cannot write them. `normalize` ignores unknown fields by design (ddf-state.js:52-53). | executed |
| L1-L3 | Copy link (overflow menu) on Compare, Find a trade, Trade targets | `DDFAssist.buildState` builds the state from the codec only (ddf-assist.js:52-78) and `siteLink` uses `DDFState.encodeQuery` (ddf-assist.js:79-82). It never calls `DDFOverrides.shareLink`, so the sender's custom basis and overrides are not in the link. The two page-local buttons do carry them: "Copy link to this search" (finder.js:1084) and league Copy link (league.js:1359). | executed |
| L4 | Copy link, sender on our methodology | No `valuecontext=1`, so a reader with a saved custom basis keeps it. | executed |
| O1 | Compare a trade link (`tradeHash`, v2.js:6143-6160) | Writes `basis=` and `ov=` but never `valuecontext=1`. The reader then merges the sender's overrides into their own saved ones: reader saved 202:30, link ov=101:58, the visit prices both. The case runs the shipped `tradeHash` and opens its link in the shipped reader. | executed |
| O2 | Compare link, sender on our methodology | No `basis=` is written for ours and no marker, so `applyLink` returns false and a reader with a saved custom basis (ESPN in the fixture) sees different values from the sender. Same writer-to-reader run as O1. | executed |
| O7 | Any link with `valuecontext=1` and a bad `basis` or `ov` | `applyLink` returns false (overrides.js:818) with no note: the whole value context is silently skipped and the reader's own settings stay. | executed |
| O8 | Override for a player not in this week's values | Kept and counted: "This link uses our methodology and 2 player overrides" when one applies. | executed |
| M1 | MCP `read_state` | Prices with our methodology and says nothing about the pasted basis or overrides (tools.ts:1106-1145; state.ts `prepare` reads only `league` and `work`). | executed, stub get-values |
| M2, M3 | Return to site (`read_state` / `make_state` `site_url` and block) | `finish` rebuilds the link from the normalized state (state.ts:87-130), so the link back drops `basis`, `ov` and `valuecontext`. | executed, stub get-values |
| S1 | `#compare-trade` link that also has `mine`, `theirs`, `target` or a name-only player (`n:`) | `readTradeHash` hands it to `DDFAssist.applyLink` and returns (v2.js:6270-6280) before `DDFOverrides.applyLink` (v2.js:6302): basis and overrides in the link are ignored. MCP links are this shape whenever a name did not resolve. | source |
| S2 | `#trade-targets` link | `DDFOverrides.applyLink` runs only for `#find-trade` (v2.js:6265) and plain Compare (v2.js:6302). A Trade targets link's basis and overrides are never applied. | source |
| S3 | Reopen the same link after "Use our methodology" | `useOurs` (overrides.js:868) keeps `linkSig`, so the same link opened again in that tab is ignored (`sig === S.linkSig`, overrides.js:815). May be intended; listed under open questions. | source |

M1-M3 pass since JEG-1343 (the MCP tools send the link's basis and overrides to get-values, name them, and keep them on the link back); the stub get-values prices a sent `ov` as get-values does.

There is no separate "Copy for AI" control on main: JEG-1101 replaced it with Copy link, which is
the AI hand-off (shell.html:96-101). Wherever the ticket says Copy for AI, read Copy link.

Guards that pass today and must keep passing: old links without any value context (C4), the
#1062 finder/league explicit default over a saved custom reader with the saved record untouched
(O3), custom blend plus adjustment round trip (O4), the same link applied twice applies once
(O5), league import Undo restoring the prior context (O6), unmarked legacy links keeping
today's reader behaviour (O1L merges a legacy Compare link's ov into the reader's saved ones;
O2L leaves the reader's settings when a legacy link has no basis or ov), and `read_state` applying league
settings (M4).

## Contract matrix

What each surface does with each field on the pinned revision. P = preserved (written and read
back), A = applied for the visit, W = rejected with a visible warning, L = lost silently,
n/a = not part of that surface.

| Field | Compare link (tradeHash) | Find a trade link | League link | Copy link (overflow) | Codec decode/encode | read_state | make_state / link back |
| -- | -- | -- | -- | -- | -- | -- | -- |
| League: scoring, teams, roster | P, A | P, A | P, A | P, A | P (bad value: W, whole league dropped) | A | P |
| League: shares, bso, inj, conf | P, A | P, A | P, A | P, A | P (bad shares: W) | A (sent to get-values) | P |
| Source week (`week`), regend, playoffs, optimize | P, A | P, A | P, A | P, A | P | A | P |
| Trade give/get | P, A | n/a | n/a | P, A | P | A | P |
| Rosters mine/theirs | n/a | P, A | P, A (teams) | P, A | P | A | P |
| Target | n/a | n/a | n/a | P, A | P | A | P |
| Finder search settings (size, km, kt, guardrails) | n/a | P, A | n/a | L | L | n/a | L |
| Custom basis | P, A | P, A | P, A | L (L1-L3) | L (C1, C3) | L (M1) | L (M2, M3) |
| Explicit default (`valuecontext=1`) | L (O2) | P, A | P, A | L (L4) | L (C2) | L | L |
| Player overrides, absolute and adjustment (packed `z:`/`z2:` past 6) | P; A merged with reader's (O1) | P, A replacing reader's | P, A replacing reader's | L | L | L | L |
| Override for an unpriced player | counted (O8) | counted (O8) | counted | n/a | n/a | n/a | n/a |
| Malformed basis or ov | partial apply of the good half | whole context skipped, no note (O7) | same as finder | n/a | n/a | n/a | n/a |
| Over-long overrides (past 1800 chars) | sender told, ov dropped | sender told, ov dropped | sender told, ov dropped | n/a | n/a | n/a | n/a |
| `src` sources, `asOf` | n/a | n/a | n/a | P; reader shows "advisory" note | P | advisory | P |
| Saved workspace and view selection | local only, never in a link | local only | local only | `view` only | `view` only | `view` only | `view` only |

### Target contract (proposed; additive and backward compatible)

1. One value context, written by one function. Every link writer (tradeHash, finder Copy link,
   league Copy link, overflow Copy link, MCP `finish`) appends the output of
   `DDFOverrides.shareLink` (or its codec twin): `valuecontext=1`, plus `basis=` when not ours,
   plus `ov=` when any. Compare links gain `valuecontext=1` (Decision D2: A).
2. The codec carries it. `DDFState` gains an optional `value` section,
   `{complete: true, basis: "<basis param>", ov: "<ov param>"}`, read from and written to the
   same three query parameters. It is opaque to the codec (no parsing of weights or packed
   bytes, so no second implementation of the Overrides rules). A reader older than the change
   keeps ignoring it, which is today's behaviour; a link without it reads exactly as today.
3. Readers apply or warn, never drop silently.
   - Site: `readTradeHash` calls `DDFOverrides.applyLink` once, first, on every state route
     (`#compare-trade` in all branches, `#trade-targets`, `#find-trade`), before rows resolve.
   - A malformed `basis` or `ov` on a complete link applies the league and work, keeps the
     reader on our methodology for the visit, and shows a note saying which part was not read.
     (Today the whole value context is skipped and the reader's own custom settings stay.)
   - Overrides for unpriced players are left out of the count and named in the note.
   - MCP `read_state` and every tool that takes `state` price under the link's basis and
     overrides (Decision D1: B, Jeremy, 2026-10-28), say in the reply which basis and how many
     overrides were used, and carry `value` unchanged into the link back. A malformed value
     context gets the same rule as the site: our methodology plus a note naming what was not read.
4. Separate concerns stay separate: the source week, basis and overrides travel in the link;
   saved workspace teams and the reader's saved view selection stay browser-local; a link never
   writes to the reader's saved settings (O3 guards this).

## Regression specs (case list)

Every case is in the harness with its expected and actual result. Cases the ticket names:

- Old links: C4 (pass), O1L and O2L (pass: unmarked legacy links keep today's reader behaviour).
- Reader with conflicting saved settings: O1, O2 (writer to reader), O3.
- Repeated use: O5 (pass), S3 (open question).
- Cancel and undo: O6 covers league import Undo (pass). League import Cancel is guarded by the
  existing #1062 render checks (`docs/claude-log/2026-10-28-league-import-undo-context.md`),
  not rerun here. "Use our methodology" then reopen is S3.
- Missing values: O8; malformed values O7.
- Copy link: L1-L4. read_state: M1, M4. Return to site: M2, M3.

Render specs to add with the fix (need the built site; Playwright, like
`tests/test_v2_share_render.py`):

- R1 (S1): open `#compare-trade?give=101&get=n:Bravo%20Wide&...&valuecontext=1&basis=fantasycalc`
  with a saved ESPN basis: the Overrides badge reads the FantasyCalc basis and the trade totals
  match the sender's.
- R2 (S2): open `#trade-targets?target=101&...&valuecontext=1&ov=101:58`: the target's DDF Value
  shows 58 with the override flag.
- R3 (L1): set a custom basis, press overflow Copy link on each of the three trade tabs, open the
  copied link in a fresh context with a different saved basis: same values as the sender.
- R4 (O7): open a complete link with `basis=notasource`: a visible note names the basis as not
  read; values are ours, not the reader's saved basis.

## Integration plan for Codex (file ownership and order)

No fix PR here. Proposed slices, each with its harness cases flipped to pass:

1. Codec (`app/v2/ddf-state.js`, `docs/design/llm-site-state.md`, `tests/node/ddf_state_check.cjs`):
   optional opaque `value` section. Flips C1-C3. Additive; existing assertions unchanged.
   Ships with Pages; the MCP function loads the served codec at cold start, so the codec itself
   needs no edge deploy (the MCP carry-through is still slice 4).
2. Overrides reader (`app/v2/overrides.js`): warn instead of silently skipping (O7), count only
   priced overrides (O8). Not a hot file.
3. Site writers and routing (`app/v2/ddf-assist.js`, `app/v2/v2.js` `tradeHash` and
   `readTradeHash`): Copy link appends `shareLink` (L1-L4; D3 decided A), Compare links write
   `valuecontext=1` (O1, O2; D2 decided A), one `applyLink` call first on every route (S1, S2).
   `v2.js` is a hot file and #1071 has it open: land after #1071 merges, then retest on the
   merged result. `league.js` is not touched (#1072 has it open).
4. Chat prices under the link's value context (JEG-1225; D1 is B). No new value math: the
   engine `get-values` already loads (`app/trade-value-chart/assets/value-model.js`) takes a
   `basisConfig` (JEG-1044, VP-6.3) and normalizes overrides (JEG-1058); the site applies both
   through `curve-widget.js` `setBasis` and `setValueOverrides`. Steps:
   - 4a. Move the link parsing (`parseBasisParam`, `parseOvParam`, the `z:`/`z2:` unpackers)
     out of `overrides.js` into one pure UMD module beside `ddf-state.js`, used by the site and
     the MCP function, so there is one reader of the link format. Covered by O4 and O7.
   - 4b. `get-values` accepts an optional basis and override map, passes the basis to the
     pipeline as `basisConfig` and applies overrides the way `setValueOverrides` does. Its
     cache key includes both. Add an endpoint parity case (`tests/test_endpoint_parity.py`
     style): same synthetic basis and overrides, site engine and `get-values` give the same
     DDF Value per player in Standard, Half PPR and PPR.
   - 4c. MCP `prepare` decodes `value`, sends it to `get-values`, every tool's reply names the
     basis and override count, and `finish` writes `value` into the link back (M1-M3).
   `get-values` and `mcp` are both edge functions: #1024 and #1032 also edit `mcp/tools.ts`, so
   integrate after them, and each deploy needs Jeremy's fresh yes naming the function. Value
   path work is T1 per AGENTS.md (it decides the numbers a chat shows).
5. AI onboarding copy (JEG-1223, PR #1078): Jeremy chose to leave the caveat out, since
   slice 4 closes the gap; no copy change is needed once it ships.

Cross-tab roster replacement on Find a trade links is JEG-1114, not this ticket.

## Decisions (all settled by Jeremy, 2026-10-28 CT)

- D1. What a chat does with a pasted link's custom basis and overrides. Decided: B (Jeremy,
  2026-10-28, "B"): the chat prices its answer under the pasted basis and overrides. Tracked
  as JEG-1225; plan in slice 4. (Options were A, carry through and say the chat uses our
  methodology; B, price under them; C, drop with a warning.)
- D2. Compare a trade links over a reader's own saved settings. Decided: A (Jeremy, 2026-10-28,
  "A"): same rule as Find a trade and league links, the sender's basis (or ours) and only the
  sender's overrides, for the visit. Compare links write `valuecontext=1` (slice 3; O1, O2).
  (Option B was to keep today's mix.)
- D3. The overflow Copy link. Decided: A (Jeremy, 2026-10-28, "A"): it carries the full value
  context like the page buttons do (slice 3; L1-L4). (Option B was to leave it out and say so.)

Open question, not blocking: after "Use our methodology", should reopening the same link in the
same tab apply it again (S3)? Today it does not.

## JEG-1254 corrections (review eddb32b1 on #1080)

Spec and harness only; no runtime file changed. All three findings still applied at head
`8ce4ae6e` (the reviewed head was `2845ba6b`; 8ce4ae6 changed only case M1, the README and the log).

1. O1/O2 now run the writer. They lift the shipped `tradeHash` out of `v2.js` (by name, read
   only), run it beside the real Overrides module holding the sender's context, and open the
   link it writes in a reader with conflicting saved settings. They pass once the writer adds
   `valuecontext=1` (slice 3, D2: A), with no reader change. The old hard-coded unmarked links
   moved to two guards, O1L and O2L, that pin today's unmarked-reader behaviour
   (overrides.js:810-825 reads only `valuecontext=1` as a complete context). Changing that is a
   legacy policy call nobody has made, so a fix that changes it fails those guards. If
   `tradeHash` is renamed or moved, O1/O2 report a harness error rather than a spec failure.
2. Unmet contract or broken harness. Only the shipped call a case is about is wrapped in
   `underTest`: its wrong answer, its throw, or a JSON-RPC error from the MCP fails the spec.
   Everything else that throws (loading a module, a fixture, a `precondition`, a writer that
   cannot be found, a case result that is not `{pass, actual}`) is `HARNESS ERROR`, exits 2 in
   the default, `--strict` and `--json` runs, and is not counted as a failing spec.
3. M2 checks every value exactly. The link back must carry exactly `valuecontext=1`, and the
   shipped reader must decode it to exactly blend ESPN 60 / Razzball 40 and a +5 adjustment on
   202: nothing missing, extra or changed. A marker-only link fails. The writer may encode ov
   plain or packed (`z:`/`z2:`); the decoded values are the contract.

Negative mutations (`harness_mutations.mjs`, in-memory edits of the shipped sources, nothing on
disk changed) show each guard rejecting the input it exists for:

| Finding | Mutation | Answer the harness must give |
| -- | -- | -- |
| 1 | W1 approved writer fix: `tradeHash` adds `valuecontext=1`, reader unchanged | O1, O2 now pass; O1L, O2L still pass |
| 1 | W2 unapproved legacy change: reader treats every link as complete | O1L, O2L regress |
| 1 | W3 writer marks the link but drops the override | O1 fails, O2 passes |
| 1 | W4 `tradeHash` renamed | O1, O2 harness error, exit 2 |
| 2 | E1 sender precondition breaks (shareParams loses the single basis) | L1, O1 harness error, exit 2 |
| 2 | E2 overrides.js throws on load; E3 Copy link module missing | harness error, exit 2 |
| 2 | E4 malformed case result, bare setup TypeError, failed precondition | harness error, exit 2 (and 2 under `--strict`) |
| 2 | E5/E6 controls: `read_state` throws or answers a JSON-RPC error | M1/M2 unmet, which differs from their record since JEG-1343, exit 1 |
| 3 | V1-V9 site_url marker only, basis only, ov only, no marker, +4, absolute 5, weights 50/50, an extra override, `valuecontext=true` | M2 fails each (exit 1 since JEG-1343) |
| 3 | V10 control: complete exact site_url | M2 passes (keeps its record, exit 0) |
