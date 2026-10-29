# JEG-1224: shared-link value basis and override loss

Bug and contract packet. Research and QA spec only: no production code, existing test or
active PR branch (#1071, #1072) is changed. Parent: JEG-1220 (normalized context plan).
Cross-tab roster precedence stays with JEG-1114. Public wording stays with JEG-1223.

## Pinned revision and how to rerun

- `main` at `021c5bfd6d631ba6ddfd4347e60d43fab71132b1` (2026-10-29 01:37 UTC), which includes
  the league finder release #1062 (complete value context on finder and league links) and the
  interactive trades release #1069.
- Harness: `tests/jeg-1224/shared_link_regressions.mjs` (Node 22, no network, no build).

```
node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs
node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs --strict
```

The first command exits 0 when every case matches its recorded state (14 failing specs, 6 passing
guards on the pinned revision). `--strict` exits 1 while any spec fails; it is the
"failing before, passing after" check for the fix. The harness loads `app/v2/ddf-state.js`,
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
| O1 | Compare a trade link (`tradeHash`, v2.js:6143-6160) | Writes `basis=` and `ov=` but never `valuecontext=1`. The reader then merges the sender's overrides into their own saved ones: reader saved 202:30, link ov=101:58, the visit prices both. | executed |
| O2 | Compare link, sender on our methodology | No `basis=` is written for ours and no marker, so `applyLink` returns false and a reader with a saved custom basis (ESPN in the fixture) sees different values from the sender. | executed |
| O7 | Any link with `valuecontext=1` and a bad `basis` or `ov` | `applyLink` returns false (overrides.js:818) with no note: the whole value context is silently skipped and the reader's own settings stay. | executed |
| O8 | Override for a player not in this week's values | Kept and counted: "This link uses our methodology and 2 player overrides" when one applies. | executed |
| M1 | MCP `read_state` | Prices with our methodology and says nothing about the pasted basis or overrides (tools.ts:1106-1145; state.ts `prepare` reads only `league` and `work`). | executed, stub get-values |
| M2, M3 | Return to site (`read_state` / `make_state` `site_url` and block) | `finish` rebuilds the link from the normalized state (state.ts:87-130), so the link back drops `basis`, `ov` and `valuecontext`. | executed, stub get-values |
| S1 | `#compare-trade` link that also has `mine`, `theirs`, `target` or a name-only player (`n:`) | `readTradeHash` hands it to `DDFAssist.applyLink` and returns (v2.js:6270-6280) before `DDFOverrides.applyLink` (v2.js:6302): basis and overrides in the link are ignored. MCP links are this shape whenever a name did not resolve. | source |
| S2 | `#trade-targets` link | `DDFOverrides.applyLink` runs only for `#find-trade` (v2.js:6265) and plain Compare (v2.js:6302). A Trade targets link's basis and overrides are never applied. | source |
| S3 | Reopen the same link after "Use our methodology" | `useOurs` (overrides.js:868) keeps `linkSig`, so the same link opened again in that tab is ignored (`sig === S.linkSig`, overrides.js:815). May be intended; listed under open questions. | source |

There is no separate "Copy for AI" control on main: JEG-1101 replaced it with Copy link, which is
the AI hand-off (shell.html:96-101). Wherever the ticket says Copy for AI, read Copy link.

Guards that pass today and must keep passing: old links without any value context (C4), the
#1062 finder/league explicit default over a saved custom reader with the saved record untouched
(O3), custom blend plus adjustment round trip (O4), the same link applied twice applies once
(O5), league import Undo restoring the prior context (O6), and `read_state` applying league
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
   plus `ov=` when any. Compare links gain `valuecontext=1` (Decision D2).
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
   - MCP `read_state` and the tools that take `state` carry `value` through to the link back
     unchanged, and say in the reply that the chat's numbers use our methodology and the
     link back opens the sender's basis and overrides (Decision D1).
4. Separate concerns stay separate: the source week, basis and overrides travel in the link;
   saved workspace teams and the reader's saved view selection stay browser-local; a link never
   writes to the reader's saved settings (O3 guards this).

## Regression specs (case list)

Every case is in the harness with its expected and actual result. Cases the ticket names:

- Old links: C4 (pass), O2 (the old Compare shape over a custom reader).
- Reader with conflicting saved settings: O1, O2, O3.
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
   `readTradeHash`): Copy link appends `shareLink` (L1-L4), Compare links write
   `valuecontext=1` (O1, O2, after D2), one `applyLink` call first on every route (S1, S2).
   `v2.js` is a hot file and #1071 has it open: land after #1071 merges, then retest on the
   merged result. `league.js` is not touched (#1072 has it open).
4. MCP (`supabase/functions/mcp/state.ts`, `tools.ts`, `tests/node/mcp_remote_check.mjs`):
   carry `value` through `prepare` and `finish`, add the reply note (M1-M3, after D1). #1024 and
   #1032 also edit `tools.ts`: integrate after them. Needs Jeremy's fresh yes naming the `mcp`
   function before any deploy.
5. AI onboarding copy (JEG-1223): until slice 4 is live, public copy must not promise that a
   chat sees the site's custom basis or overrides.

Cross-tab roster replacement on Find a trade links is JEG-1114, not this ticket.

## Decisions for Jeremy

- D1. What a chat does with a pasted link's custom basis and overrides.
  A) Carry them through to the link back and say the chat's numbers use our methodology
  (recommended: honest, no new math, small change).
  B) Price the chat's answer under the pasted basis and overrides (new get-values path, bigger).
  C) Drop them with a warning.
- D2. Compare a trade links over a reader's own saved settings.
  A) Same as Find a trade and league links: the sender's basis, or ours, and only the sender's
  overrides, for the visit (recommended: one rule everywhere).
  B) Keep today's mix: sender's overrides added to the reader's own.
- D3. The overflow Copy link.
  A) Carry the full value context like the page buttons do (recommended).
  B) Leave it out and add a line saying the link uses our methodology.

Open question, not blocking: after "Use our methodology", should reopening the same link in the
same tab apply it again (S3)? Today it does not.
