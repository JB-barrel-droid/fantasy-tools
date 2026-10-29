# Homepage AI onboarding: copy pack and capability checklist

Draft for Jeremy's review (JEG-1223, part of JEG-1137). Nothing here publishes. It feeds the Codex-owned design preview: strings and checks only, no layout, design choice, runtime change or deploy. Terminology for DDF Value and the value views stays with JEG-1212; this copy avoids defining DDF Value so it survives that decision.

Checked 2026-10-29 (UTC) against `origin/main` 021c5bfd and the live DDF connector. Values in the live answers were dated 2026-10-28.

## Evidence levels

| Code | Meaning |
|---|---|
| **S** | Source inspection of `origin/main` 021c5bfd. Says what the code does, not what is deployed. |
| **L** | Live API call to the deployed DDF MCP server through a Claude agent session's DDF connector, 2026-10-29 about 01:45 UTC. Not the claude.ai or ChatGPT consumer app. |
| **V** | Vendor setup docs read 2026-10-29 (links below). |
| **R** | Recorded earlier finding in Linear or `docs/claude-log/`, not repeated here. |
| **C** | Real ChatGPT or Claude consumer-client test. **None performed** for this ticket, and none is recorded for the link round trip (JEG-1026, JEG-1101 both list it as not verified). No string below may imply one. |

Not reachable from this environment: the live site (`jb-barrel-droid.github.io`) and a direct HTTP call to the MCP URL were both refused by the network policy. Site claims rest on source (S) and the 2026-10-26 live check (R); the `connect/` page is not re-verified today.

## Copy pack

IDs are for the implementer. Every string is a draft for Jeremy. Destinations are exact.

### Homepage block (first-time visitor)

| ID | String | Destination |
|---|---|---|
| `ai.h` | Use DDF in Claude or ChatGPT | none |
| `ai.body` | Connect the DDF tool once. Then ask about trades in plain words and get Data Driven Football values for your scoring, team count and superflex setting, with a link back to the same view here. | none |
| `ai.cta` | Connect the tool | `https://jb-barrel-droid.github.io/fantasy-tools/connect/` |
| `ai.cta.note` | Free, no account, no sign-in. You add one web address as a custom connector. | none |

### Connected-user next step

The site cannot tell whether a reader's chat is connected, so this line is conditional in its own words and never shown as a detected state.

| ID | String |
|---|---|
| `ai.next.h` | Already connected? Try asking: |
| `ai.next.ex1` | "Using Data Driven Football, is Bijan Robinson for Ja'Marr Chase fair in my 12-team half-PPR league? Give me the link to open it on the site." |
| `ai.next.ex2` | "Using Data Driven Football, who are fair 1-for-1 trade targets for Puka Nacua in a 12-team half-PPR league?" |
| `ai.next.note` | Each answer says the date of the values and ends with a link to the same view here. |

`ex1` runs `compare_trade` (a value sum) and returns `site_url`; `ex2` runs `trade_targets`. Both were run live (L). Player names are examples only: swap them if a name drops out of the data before launch.

### Copy link (sharing, later and separate from connecting)

| ID | String | Where |
|---|---|---|
| `ai.link.line` | Opens this view. A chat with the DDF tool reads it too. | Existing line under Copy link (Jeremy's 2026-10-27 pick A). Unchanged. |
| `ai.link.more` | Copy link puts this view's address on your clipboard: your league settings and the trade, rosters or target you're working on. Paste it into a chat that has the DDF tool connected and it picks up from there. Pasting a link does not connect the tool. | Connect page and any ⓘ, if the design wants a longer form |
| `ai.link.local` | Your saved work stays in this browser. A link carries only what is in its address. | Same |

### Fallback and error text

| ID | When | String |
|---|---|---|
| `ai.err.copy` | Clipboard write fails | Couldn't copy. Copy this link: `<url>` (matches today's fallback, `v2.js` `Copy this link:`) |
| `ai.err.notconnected` | Help text on the connect page | If the chat answers without Data Driven Football numbers or a site link, the tool isn't connected in that chat. [Connect the tool](https://jb-barrel-droid.github.io/fantasy-tools/connect/) |
| `ai.err.names` | Help text | Names the tool can't match are listed so you can fix the spelling. It doesn't guess between players with the same name. |
| `ai.err.league` | Help text | The tool covers 8, 10, 12 and 14 teams, with standard, half PPR or PPR scoring, superflex or not. |
| `ai.err.busy` | Help text | The tool is free and shared. If a chat says it's busy, wait a minute and ask again. |

## Three separations the copy keeps

| Topic | Side A | Side B | Copy that keeps them apart |
|---|---|---|---|
| Connect vs share | Connecting is a one-time setup in the chat app (custom connector URL). | Sharing is pasting a site link into a chat that is already connected. | `ai.cta`, `ai.link.more` ("Pasting a link does not connect the tool.") |
| Browser-local vs link-carried | Workspaces and overrides are saved in this browser's localStorage (`workspace.js` line 11, `overrides.js`). | A link carries league settings, work lists, and on Compare a trade `basis=`/`ov=` (`v2.js` `tradeHash`). | `ai.link.local` |
| Site vs connector | Site: lineup-aware Compare, per-chart columns, value basis and overrides, league-wide finder UI. | Connector: values by name, trade sum, 1-for-1 targets, finder between rosters or across a league, read and make links, explain. | No homepage string claims site features in chat |

## Claim → evidence → limitation

| # | Claim the copy makes | Evidence | Level | Limitation |
|---|---|---|---|---|
| 1 | One URL adds DDF as a custom connector, no sign-in | `supabase/config.toml` `[functions.mcp] verify_jwt = false`; no auth in `mcp/index.ts`; Claude docs allow "No sign-in" custom connectors | S, V | Not client-tested. ChatGPT's page does not say whether no-auth servers are allowed. Free Claude accounts can add one custom connector (V). |
| 2 | Works with Claude and ChatGPT | Both vendors document adding a remote MCP server by URL | V | No consumer-client test (C: none). Copy says "add as a custom connector", never "tested in" or "works the same in". |
| 3 | Values follow scoring, team count, superflex | Live answers carried `setting` for half PPR/12, standard/10, standard/14/superflex | L | Team counts limited to 8, 10, 12, 14 (tool schema). |
| 4 | Each answer gives the date and a link back | Every live result had `as_of` 2026-10-28 and a `site_url` | L | The link is a site view, not a saved copy of the chat's reasoning. |
| 5 | Ask about a trade in plain words | `compare_trade` live: Bijan vs Chase, standard 10-team, 75.2 vs 40.1 | L | Sum of DDF Values only: not lineup-aware, no per-chart breakdown (the tool's own description says so). Copy must not say "full trade analysis". |
| 6 | Fair 1-for-1 targets | `trade_targets` live: Puka Nacua, half PPR 12-team, six targets within 15% | L | DDF Value only. |
| 7 | A site link carries league and work into a connected chat | `read_state` live on a Compare link resolved both players (player keys 217, 2730) | L | JEG-1157 (empty player list) is Done and no longer reproduces. |
| 8 | A link does not carry your custom values into the chat | `read_state` live on the same link plus `basis=fantasycalc&ov=217:+20` returned identical values (Bijan 67.6) with an empty `notes` list, and the returned `site_url` dropped `basis` and `ov` | L, S | **Known gap.** Silent: no warning to the chat. A link handed back by the chat also loses the reader's basis and overrides. Jeremy, 2026-10-28 CT: "we should fix the tech, and leave it out." The fix is JEG-1225; the copy carries no caveat. Detailed reproduction belongs to the shared-link child spec. |
| 9 | Saved work stays in this browser | `workspace.js` "Saved in this browser only (localStorage key ddf.v2.workspaces)" | S | Private browsing or cleared site data loses it. |
| 10 | Unmatched names are listed, not guessed | `get_player_value` live: "Zzyzx Player: NOT FOUND"; "Allen: AMBIGUOUS" with five suggestions | L | Partial names auto-match when only one player fits ("Bijan" matched Bijan Robinson). |
| 11 | Free and shared, may be busy | 60 requests a minute per IP in `mcp/index.ts`, returns "rate limited" | S | Not load-tested. Copy avoids the number. |
| 12 | The connect guide is at `connect/` | Built by `pipelines/build_llm_surfaces.py`; returned 200 on 2026-10-26 | S, R | Not re-verified today (site unreachable from here). |

## Claims to remove or fix (flagged, not changed here)

1. **Connect guide menu paths are stale.** `docs/use-ddf-in-claude-chatgpt.md` says Claude "Settings, Connectors" and ChatGPT "apps / developer mode". Claude's docs now say **Customize > Connectors > Add custom connector**; OpenAI's Apps SDK page says **chatgpt.com/plugins > + > Add custom MCP server**. Suggest the guide link the vendor pages instead of restating menus, with a checked-on date. Owner: whoever next edits the guide (Codex for shared-file integration).
2. **Tool count.** The guide lists 7 tools; the live server and `llms.txt` have 9 (`find_trades`, `find_trades_league` missing from the guide).
3. **DDF Value definition.** The connector, `llms.txt` and `get_values` say "the average of the four adjusted trade charts". Jeremy's Oct 28 wording is the average of the weight-adjusted indexed values, not the trade chart average. The live result also lists seven sources included. Flag for JEG-1212; this copy pack defines nothing.
4. **No lineup-aware or per-chart claim for chat** (claim 5), and **no claim that chat honors custom values** (claim 8) until JEG-1225 lands.
5. **No account import.** No string names Sleeper, ESPN or Yahoo as an integration. Rosters reach the tool as names the user pastes (JEG-1137: "Platform names explain copying, never claim integrations").
6. **The Claude skill is optional.** The guide asks Claude users to upload `ddf-skill.zip`. The homepage should not present it as a required step; the server's own instructions carry the same guidance (S: `llms.txt`, guide).
7. **No equal-numbers promise.** Leagues with settings the tool doesn't apply get a note in the answer; never say the chat matches the site exactly.

## Acceptance checks for the implementer

1. Every string in the copy pack appears verbatim, or with Jeremy's edits, and no other AI claim is added.
2. `ai.cta` and `ai.err.notconnected` link exactly `https://jb-barrel-droid.github.io/fantasy-tools/connect/`, the same href as the footer's `Connect the tool` (the existing `test_v2_assist_render` footer check).
3. No homepage or Copy link string contains "tested", "import", "sync", "automatic", "same numbers", "lineup", "Sleeper", "ESPN" or "Yahoo". A grep over the built page's AI block passes.
4. The connected-user step never reads as a detected state: no checkmark, "you're connected" or similar.
5. No string says or implies that the chat uses the reader's value basis or player overrides. Revisit when JEG-1225 ships and the live `read_state` check in claim 8 returns the custom values.
6. Before launch, re-run both example prompts through the live connector and confirm each still returns a value and a `site_url`; swap names if not.
7. A real Claude and ChatGPT client test of connect, ask and link round trip is recorded before any string says more than "add as a custom connector".

## Decisions for Jeremy

1. **The custom-values caveat: decided.** Jeremy, 2026-10-28 CT: "we should fix the tech, and leave it out. File a ticket to fix the tech." No caveat string; the connector fix is JEG-1225.
2. **Headline (open).** **A: "Use DDF in Claude or ChatGPT" (my pick: names both apps and the action).** B: "Ask Claude or ChatGPT, with DDF numbers."

## Sources

- Claude custom connectors: https://www.claude.com/docs/connectors/custom/remote-mcp (read 2026-10-29)
- ChatGPT, connect a custom MCP server: https://developers.openai.com/apps-sdk/deploy/connect-chatgpt (read 2026-10-29)
- Repo: `supabase/functions/mcp/tools.ts`, `index.ts`, `supabase/config.toml`, `app/v2/v2.js`, `app/v2/workspace.js`, `app/v2/overrides.js`, `app/v2/shell.html`, `app/llm/llms.txt`, `docs/use-ddf-in-claude-chatgpt.md`, `docs/claude-log/2026-10-26-jeg-1101-llm-buttons-explained.md`
- Linear: JEG-1026 comments (live check 2026-10-26), JEG-1157 (Done 2026-10-28), JEG-1137, JEG-1212
