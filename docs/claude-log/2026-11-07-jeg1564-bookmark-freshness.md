## 2026-11-07 - JEG-1564 Bookmark prompts, league names, titles, roster freshness

Contract (Jeremy, 2026-11-07): prompt for a bookmark after big inputs, overwriting old bookmarks in one click if
possible; helpful bookmark titles; let users name leagues and carry the name into bookmarks; keep the input date so a
week-old bookmark prompts a roster refresh. Same-day additions: graduated freshness bands instead of one 7-day cliff;
league name, ID and platform read from the paste ("We found: ..."); the header pill shows the league name, abbreviated
to fit. Client-side only, no analytics, the link codec stays backward compatible.

Feasibility (sources in the PR body)
- A web page cannot create, edit or replace a browser bookmark in any current browser (IE AddFavorite and Firefox
  sidebar.addPanel are gone; chrome.bookmarks is extension-only). So there is no one-click overwrite.
- Browsers name a new bookmark from document.title at the moment the dialog opens, so the title scheme matters.
- Chrome and Firefox match an existing bookmark by the exact URL, fragment included: a stable URL shows as already
  bookmarked (no duplicate); a new `#s=` token is a new bookmark. Safari can make duplicates either way.
- What ships: (1) Bookmark keeps putting a portable `#s=` link in the address bar (works on any device), now carrying the
  pasted league's teams, team, name and date; (2) "Keep one bookmark on this device instead" swaps the address to the
  plain page URL, which always opens the latest saved league on this device, so one bookmark never needs replacing;
  (3) device-specific how-to (Cmd+D, Ctrl+D, iOS Share > Add Bookmark, Android menu star), as before.

What changed
- `app/next/site.js`
  - `DDF.leagueMeta` (one helper, every surface): league name (default "My league"), team, `enteredAt`, age in plain
    words, freshness band from one `FRESHNESS` config, the banner at the top of each workspace page, the chip age line,
    and `document.title` = "League – Team – Week N – Data Driven Football" (league cut at 28 chars, team at 22).
  - Bands: 0-1 day nothing (yesterday's roster is current), 2-3 a quiet line, 4-6 a gentle prompt with "Update rosters"
    (most of a week of waiver and injury moves), 7+ a banner saying trade values and lineup effects may be off and
    "Paste rosters again" (a full NFL week or more). Dismissals are per band per session (`ddf:freshdismiss:<band>`),
    so dismissing a weaker band never hides a stronger one.
  - Header chip: the league name, fitted (full name, then "USO S. XVIII"-style when a later word is an acronym, number
    or roman numeral, then whole words with an ellipsis, then characters). Max 120px under 768px wide, 200px above,
    and never wider than the header has room for. Full name in the tooltip, aria-label and menu; "Your league" fallback.
  - Bookmark prompt after a big input (rosters read, team confirmed, settings confirmed, 3+ override changes): one
    prompt per change (`ddf:bmwant` / `ddf:bmdone`), shown when the Bookmark button is on screen, closes after 20s,
    never blocks. On settings.html the prompt waits for the next page (that page navigates away at once).
  - Bookmark link: the chat league when it has teams; otherwise the pasted or saved league plus the reader's saved
    engine settings, so the button also shows for a saved league.
  - Codec: `name` (1-40 chars) and `enteredAt` (YYYY-MM-DD) in the JSON body; readers drop bad values, writers reject.
- `rosterparse.js` `league()`: Yahoo "Name (ID# n)" header, ESPN "League Rosters" + name line, "League ID" + number,
  leagueId= / /f1/ / /leagues/ addresses; platform for Yahoo, ESPN, Sleeper, CBS. Section headings, game lines and team
  names are never a league name. Sleeper and CBS header names are not read (format not verified).
- connect: "We found: <name> · ID# <n>" on the card; `ddf:pasted` gets `enteredAt`, `suggestedName`, `leagueId`,
  `platform`. setup: "Name this league (optional)", prefilled with the suggestion and labelled as found in the paste;
  saved only when the reader edits it or presses Next (an untouched suggestion is never saved on its own); the bridge writes name, date and ID to the saved
  league. The league ID stays on the device.

### Verified (check named)
- `node tests/test_entry_league_paste.js` (32 pass): adds league-header cases on 7 fixtures, headings/team names never a
  league name, record carries a suggestion and never a saved name.
- `tests.test_bookmark_freshness` (9 pass; the link-overrides test fails without the fix): band boundaries 0/1/2/3/4/6/7/8 days and plain-word ages; banner per band,
  dismissing the prompt band keeps the stale band; title scheme and "My league"; prompt once per change; chip fit for
  short/long/very long/emoji names at 390 and 1440 with no header overflow, aria-label, fallback; codec round trip, old
  vector decodes, bad values dropped/rejected; the Bookmark link carries the pasted league; setup suggests, saves on
  edit or Next; a link's overrides never ask for a bookmark; the league ID is not in the link or the title.
- `tests.test_entry_pages`, `tests.test_build_root_pages`, `tests.test_launch_copy_guard`: 40 pass.
- `09-mcp-server/test/league_meta_test.ts` (handoff folder, Deno, against the repo site.js): 3 pass; the whole handoff
  mcp suite 51 pass.

Review fixes (independent review of a4a30e7a, CHANGES NEEDED): a link's overrides no longer count as edits;
"Keep one bookmark on this device" only for the saved or bridged league; a settings-only chat state lends no name,
date or team; 1-team pastes read the same in the chip and the link; names cleaned by code points; chip re-fit after
fonts load; no generic hint on settings.html right after confirm.

### Claimed, not confirmed
- CI on the PR head; live behaviour after deploy (verify_live.py and a live Playwright pass follow the merge).
- The repo's mcp function is still the pre-v25 copy until JEG-1541; the v25 reader keeps the new keys (Deno test).
