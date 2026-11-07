## 2026-11-06 - JEG-1538 Entry pages at the live root (connect, setup), real paste reader, link codec routes

Contract: plan step 4 of JEG-1534. Put the redesigned entry pages on the live root, fed by the live engine and the live
paste parser; the recognition card, "Which team is yours?" and the failure paths come from the real parse; the
link codec (site.js, already at the root since JEG-1535) gets regression tests on its published vectors; old routes
forward keeping link state. Jeremy (2026-11-06): auto-merge each swap step when all gates and an independent review
pass. Additions from Jeremy the same day: iPhone copy tip by the paste box; per-app league ID steps with his blurred
Yahoo and ESPN screenshots (League ID left visible); device-aware copy steps with "On a phone" / "On a computer".
DDF_APP_ORIGIN is NOT set here: JEG-1541 (mcp v25 into the repo) must merge first.

What changed
- `app/next/league-paste.js` (new): reads a pasted league with the live `v2/roster-paste.js` (`parseLeague`, and
  `extractPlayers` per team block) and the redesign's `rosterparse.js` (team names from Yahoo phone tab text, Yahoo
  markdown, CSV, "Team: a, b" lines, rank prefixes). The result with more matched players wins, so every page the live
  League tab reads reads the same (parity test). `readWithNames()` backs the edit-names box.
- `app/next/connect-entry.js` (new) + `connect.html`: "Check my rosters" (or a paste) fills "Here's what we read from
  your paste" from the parse (per team: matched lines, Needs a look, Not found, Not evaluated for K/DEF); the static
  "12 teams found..." card and the sample manual roster are gone. Unreadable paste: status line plus "Check your team
  names" box (type names, read again). One team's page: the existing one-team notice. Manual entry: team names, then
  players found by name on the engine's player list. League kept in sessionStorage `ddf:pasted`
  `{v, source, site, teams:[{name, players:[{name,key,pos,team,slot,line,id}], unmatched:[{line,reason,pos}]}], me}`;
  a new paste clears a chat-link league (`DDF.link.clear()`). Next needs a read league (2+ teams) or a link.
- League ID help (collapsed, follows the provider toggle): ESPN app (League tab, League Info, League ID under Basic
  Settings; support.espn.com "League ID" article + Jeremy's screenshots), Yahoo app (League tab, settings gear, League
  ID# first row; Jeremy's screenshots, help.yahoo.com SLN8238 for the web path), Sleeper app (League Settings, General
  League Settings, Copy League ID; support.sleeper.com "How to find your league ID"), each with its web-address
  pattern. Screenshots cropped to the relevant part (drops a visible division name and an ad), 600px JPEG, lazy.
- Device: `html[data-device]` from `(pointer: coarse)` / `(max-width: 760px)` and the user agent, local only; unsure =
  both versions show. iPhone tip by the paste box; Yahoo phone copy steps (Safari long-press, Select All, Copy, which
  Jeremy used on his own league). ESPN and Sleeper keep the computer steps on every device (phone steps unverified).
- `app/next/setup-entry.js` (new) + `setup.html`: teams from `ddf:pasted` or a chat link's teams; none = "No rosters
  added yet" with a link back. Confirming a team stores `me` and (storage bridge, plan D4) writes the league to the
  live `ddf.v2.workspaces` (keeps the live league's id, name, settings, view choices; replaces its teams), so the live
  Find a trade and league pages show it until JEG-1539.
- `pipelines/build_root_pages.py`: connect.html and setup.html join ROOT_PAGES (connect carries the engine), plus their
  files, `assets/howto` and `img/league-id`. Links to them are no longer rewritten; /next/ copies become redirects.
- `app/v2/v2.js`: a `#s=` token on a v2 route goes whole to connect.html (was values.html), where site.js opens the
  link's page. `app/next/site.js`: a view whose page is not live yet maps to a live hash route at the root; the token
  is no longer appended after that hash (it made `./#compare-trade#s=...`, which v2 treated as unknown); the league
  stays in the tab store instead.
- AI prompts: the NO-TOOLS line now sends users to `connect.html` (was the MCP guide at `connect/`), in all five page
  copies (`08-ai-module` .txt files and `sync-prompts.py` in the handoff folder).

### Verified (check named)
- `node tests/test_entry_league_paste.js`: parity with `parseLeague` on the 4 live league fixtures (names and player
  keys), 12 redesign fixtures incl. the real iPhone tab text and Yahoo markdown pastes (names scrubbed): team names and
  matched players per team, edit-names path, record shape (20 pass).
- `tests.test_entry_pages` (9 pass): build lists, prompts, no static sample; paste -> card; unreadable -> edit names;
  setup -> `me` + live store; LINK-FORMAT 6 and 6.1 vectors decode to the documented states and an encode/decode round
  trip keeps teams, me, overrides, basis; `#s=` on a v2 route -> connect.html; /next/ stubs keep query and hash;
  a check-view link opens `#compare-trade` with the league kept; ID help follows provider, screenshots load; iPhone UA
  shows the tip, 0 overflow at 390.
- `tests.test_values_swap_routes` (token test now expects connect.html), `tests.test_build_root_pages`,
  `tests.test_next_preview`: 42 pass. `node tests/test_v2_league_paste.js`, `node tests/test_v2_roster_paste.js` pass.
- QA sweep (`scratchpad/qa1538.py`, Chrome, 1440x900 desktop, 390x844 iPhone UA, 390x844 desktop UA): 0 console
  errors, 0 page errors, 0 failed requests, 0 horizontal overflow on connect (empty, ID help open, card) and setup;
  redirects 3/3.

### Claimed, not confirmed
- CI (`make validate`, test-core shards, rendered gate) on the PR head: see the PR checks.
- Live behaviour after deploy: pending `verify_live.py` and a live Playwright pass.
- `CompressionStream('deflate-raw')` on the edge runtime and DDF_APP_ORIGIN: after JEG-1541.
