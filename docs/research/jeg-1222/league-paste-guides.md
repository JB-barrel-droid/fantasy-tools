# League-paste guides: ESPN, Yahoo, Sleeper (JEG-1222)

Fact-checked desktop copy for loading a league into Data Driven Football by
copy and paste, with the evidence behind each step. Prepared 2026-10-29 UTC
against `main` at `021c5bf`. Copy and research only: no parser, runtime copy
(JEG-1130) or design (JEG-1137) change.

## Answer first

| Platform | Whole league in one paste | One team per paste | Guide status |
| -- | -- | -- | -- |
| ESPN | Path verified (League, then Rosters). Copied-text layout **not** verified: the fixture's layout is inferred. | Verified on a real capture | Ship the one-team guide; ship the whole-league guide marked "check the count" until a real capture lands |
| Yahoo | A "Starting Rosters" page with every team exists. Copied-text layout **not** verified; the fixture's layout is inferred and differs from what that page shows | Verified on a real capture (My Team, then Roster) | Ship the one-team guide only |
| Sleeper | Not verified. No all-rosters page confirmed on the web | Not verified on a real capture | Ship the one-team guide with a clear "may need fixing" note, or hold |

Two findings change the starting evidence in the ticket:

1. **No whole-league fixture is a real capture, ESPN included.** PR #913
   (2026-10-25), which added all three, says: "exact copied-text layout of
   each site's league page is inferred (ESPN fixture uses real rosters from
   Jeremy's screenshot)." The ESPN rosters are real; the line-by-line text a
   browser copies from ESPN's Rosters page is a reconstruction. The test file
   header (`tests/test_v2_league_paste.js`) reads as if ESPN were a real paste.
2. **The live help copy promises more than the evidence supports** (see
   "Live copy issues" below): Yahoo whole-league paste, phone copy, and
   Windows keys only.

## Where pasted text goes in DDF (all platforms)

- **Whole league:** *Find a trade: league-wide* (`v2/#find-league`), the box
  "Load a whole league: paste its rosters page". A paste there is read at
  once; nothing to press. Up to 20 teams.
- **One team at a time:** on the same page press **Add team**, then paste into
  that team's box ("Search a player, or paste a team page"). For a single
  opponent, *Find a trade: your team* (`v2/#find-trade`) takes one roster per
  side.
- **Kept on this device only.** Rosters save in this browser. Nothing is sent,
  synced or linked to the fantasy site. A pasted league link is not opened:
  it holds no rosters (JEG-1131), and DDF says so.

## What the person sees after pasting (all platforms)

Wording below is quoted from `app/v2/league.js` on `021c5bf`.

- Whole league: "Read N teams from your paste." Then each team's name and
  player count, "your team" beside the starred team, and "N to check" where a
  name match is unsure.
- Unmatched lines are listed under each team: "N lines not matched to a
  player:" and the closing line "Add those players by searching inside the
  team." When all match: "Every player line was matched."
- Kickers and defenses are kept as listed but not valued.
- One-team paste: "Matched X of Y players." Unsure matches ask "Pasted
  '...': is this [player]?" with yes and no; they are not added until
  answered. Unmatched names: "Not matched (N): add them by search."
- Pasting the same league again updates teams with the same name instead of
  adding duplicates.

**Repair steps (same everywhere):** open the team with a "to check" or "not
matched" note, answer each "is this...?" question, then type any missing
player's name in that team's box and pick them from the list. Press the star
beside your own team.

---

## ESPN (desktop browser)

### A. Whole league (verified path, unverified text layout)

1. Sign in at ESPN Fantasy Football on a computer and open your league.
2. In the **League** menu at the top, choose **Rosters**. The page is headed
   "League Rosters" and shows every team, each with a Propose Trade button.
3. Click anywhere on the page body (not in the search box), press **Ctrl+A**
   then **Ctrl+C** (Mac: **Cmd+A**, **Cmd+C**).
4. In DDF open *Find a trade: league-wide* and paste into "Load a whole league:
   paste its rosters page" (**Ctrl+V** / **Cmd+V**).
5. Check the count: "Read N teams from your paste" should equal your league
   size, and each team should show a full roster. If it does not, use path B
   for the teams that came out short.
6. Press the star beside your team. Fix any "to check" or "not matched" lines
   (repair steps above).

Imports: every team on the page, one paste.

### B. One team at a time (verified on a real capture)

1. Open **My Team** (or a rival's team page) on ESPN.
2. **Ctrl+A**, **Ctrl+C** (Mac: **Cmd+A**, **Cmd+C**).
3. In DDF press **Add team**, name it if needed, and paste into its box.
4. Expect "Matched X of Y players." Repeat for each team.

Imports: one team per paste. A matchup page holds two teams and DDF asks
"Which team is this?".

## Yahoo (desktop browser)

### A. One team at a time (verified on a real capture)

1. Sign in at Yahoo Fantasy Football on a computer and open your league.
2. Hover **My Team** and choose **Roster** (Yahoo help SLN7137). For a rival,
   open their team from the league.
3. **Ctrl+A**, **Ctrl+C** (Mac: **Cmd+A**, **Cmd+C**).
4. In DDF press **Add team** on *Find a trade: league-wide* and paste into
   that team's box, or use *Find a trade: your team* for one opponent.
5. Expect "Matched X of Y players." Repeat for each team.

Imports: one team per paste.

### B. Whole league: not ready for the guide

Yahoo has a page titled **Starting Rosters** (address ends `/starters`) that
lists every team's starters and bench, with Team and Position tabs and a week
picker. Seen on Yahoo's public demo league (`/f1/101/starters`) on
2026-10-29. Not yet shown to work:

- Where it sits in the League menu was not confirmed.
- No copied text from a signed-in league exists. The repo's Yahoo league
  fixture is inferred, and its headers ("Pos / Offense / Action / Forecast",
  separate Kickers and Defense tables, an IR row) match the **My Team** page,
  not what the Starting Rosters page showed (Pos and Player columns, no
  separate kicker/defense captions, no IR row seen).
- Team names there carry no record like "(5-1-0)", so the parser would have
  to split teams by table header only.

Until a real paste is captured and tested, the guide should not tell Yahoo
users to paste the whole league.

## Sleeper (desktop browser)

### A. One team at a time (unverified)

1. Sign in at sleeper.com on a computer and open your league.
2. Open the team you want (yours, or a rival's from the league's team list).
3. **Ctrl+A**, **Ctrl+C** (Mac: **Cmd+A**, **Cmd+C**).
4. In DDF press **Add team** and paste into that team's box.
5. Expect "Matched X of Y players"; add any missing player by name.

Imports: one team per paste. Gaps: the exact Sleeper web screen and its copied
text were not checked (signed-in), and the parser has no real Sleeper capture;
only a short hand-written test string. Recommend either holding this guide or
shipping it with "if few players match, add them by name".

### B. Whole league: not verified

No Sleeper web page that lists every roster at once was confirmed. Sleeper's
help (article 4238825, dated 2026-09-24) says the web **Trades** tab, then
**Trade**, opens a "full roster view", but not whether that shows every team
at once. A user request for "a league feature that allows you to view all
rosters on one screen" has no staff reply. The repo's Sleeper league fixture
(name, @handle, record per team) is inferred. The live site already tells
Sleeper users to paste one team at a time, which matches the evidence.

---

## Verification table

| Platform / path | Evidence | Date | Scope | Limitations | Result |
| -- | -- | -- | -- | -- | -- |
| ESPN League > Rosters, menu path | ESPN Fantasy 101 "League and team pages" (League tabs include Rosters; "view the rosters of all teams"; Propose Trade per team). Real ESPN capture `tests/fixtures/roster_paste/espn-team.txt` lists League > Rosters in its menu | Article 2022-06-30; capture 2026-10-22 | Whole league | Article is old; menu confirmed by the 2026-10 capture | **Pass** |
| ESPN League > Rosters, copied text | `tests/fixtures/league_paste/espn-league-rosters.txt` and `-split-record.txt`; `node tests/test_v2_league_paste.js` 12/12 | Fixture 2026-10-25 (PR #913); run 2026-10-29 | Whole league | Layout inferred from a screenshot (PR #913), not a Ctrl+A capture | **Blocked**: needs a real capture |
| ESPN team / matchup page | `tests/fixtures/roster_paste/espn-team.txt`, `espn-matchup.txt`, real scrubbed captures (PR #804) | 2026-10-22 | One team; matchup = two | Single league's settings | **Pass** |
| Yahoo My Team > Roster | Yahoo help SLN7137; real scrubbed capture `tests/fixtures/roster_paste/yahoo-team.txt` (PR #804) | Help read 2026-10-29; capture 2026-10-22 | One team | Single league's settings | **Pass** |
| Yahoo Starting Rosters | Yahoo public demo league page `/f1/101/starters` (title, every team, starters + bench, tabs, week picker) | 2026-10-29 | Whole league | Not signed in; menu location unconfirmed; no copied text; repo fixture inferred and shaped like My Team | **Blocked** |
| Sleeper team page | Hand-written string in `tests/test_v2_finder_paste_render.py` only | n/a | One team | No real capture; screen not seen | **Blocked** |
| Sleeper whole league | Sleeper help 4238825; community request; inferred fixture `sleeper-league-rosters.txt` | Help 2026-09-24; read 2026-10-29 | Whole league | No all-rosters page confirmed | **Blocked** |
| Pasted links not fetched | `parseLeague` reads a Sleeper/ESPN league ID but makes no request; `tests/test_v2_paste_only_render.py` | Main `021c5bf` | All | none | **Pass** |
| Device-only storage | League saved in this browser; help copy "Pasted text stays on this device" | Main `021c5bf` | All | none | **Pass** |

Sign-ins: none made. ESPN, Yahoo and Sleeper were not signed in to for this
ticket; every "signed-in" screen above is listed as missing evidence.

## Screenshots

None are supplied with this ticket. No screenshot was captured or inspected,
and none should be mocked. Missing shots, each to be taken on a desktop
browser with team, manager and league names blurred:

1. ESPN: League menu open with Rosters highlighted.
2. ESPN: top of the League Rosters page (heading and first team).
3. Yahoo: My Team menu with Roster highlighted.
4. Yahoo: top of a team's Roster page.
5. Yahoo: Starting Rosters page and where it sits in the League menu (only if
   the whole-league path is later verified).
6. Sleeper: the screen that shows one team's roster, and how it is reached.
7. DDF: "Load a whole league" box before paste.
8. DDF: "Read N teams from your paste" summary with one "not matched" line.
9. DDF: a team box with an "is this...?" question.

## Real captures needed to close the blocked rows

Each is a Ctrl+A, Ctrl+C paste from a signed-in desktop browser, saved as a
text file with names scrubbed, to go into `tests/fixtures/league_paste/` with a
test (Codex owns parser and fixture integration):

1. ESPN League > Rosters page.
2. Yahoo Starting Rosters page (Team tab), plus where its link sits.
3. Sleeper: one team's roster page, and the Trades > Trade "full roster
   view" to see whether it lists every team.

Jeremy's own leagues could supply these in a couple of minutes each.

## Live copy issues (for JEG-1130 / Codex; not changed here)

Quoted from `app/v2/league.js` on `021c5bf`:

- Line 1417, "Yahoo: your league's rosters page." Tells Yahoo users to paste a
  whole league, which is unverified. Suggest one team per paste for Yahoo
  until a real capture passes.
- Line 1417, "(on a phone, select all and copy)". Phone import was not
  checked on any platform; the ticket asks not to promise it.
- Lines 122, 261, 610 and 1417 give only "Ctrl+A ... Ctrl+C". Add "Cmd+A,
  Cmd+C on a Mac".
- Line 1408 placeholder "(ESPN, Yahoo or any site)" has the same Yahoo issue.
- `tests/test_v2_league_paste.js` header says the ESPN rosters are "a real
  league's"; true of the players, not of the copied layout. Worth one word of
  correction so the next reader does not treat it as a capture.

## Sources

- ESPN Fantasy 101, League and team pages: https://www.espn.co.uk/fantasy/football/story/_/id/19541264/league-team-pages
- Yahoo help, Roster and lineup management: https://help.yahoo.com/kb/SLN7137.html
- Yahoo help, League tab (Fantasy Hockey, same layout): https://help.yahoo.com/kb/SLN26585.html
- Yahoo Starting Rosters, public demo league: https://football.fantasysports.yahoo.com/f1/101/starters
- Sleeper help, new trading experience: https://support.sleeper.com/en/articles/4238825-welcome-to-a-new-trading-experience
- Sleeper community request, all rosters on one screen: https://sleeper.com/message/170000000000000000/903444015566147584/903446587366531072
- Repo: PR #804 (team-page captures), PR #913 (league fixtures, "layout is inferred")
