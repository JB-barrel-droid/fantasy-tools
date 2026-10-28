# Data Driven Football picks log (repo copy)

Decisions the Claude lanes made on Jeremy's behalf, so he can reverse any of
them. Jeremy, 2026-10-27 9:45 PM CT: "Yes, use your picks, and make a note of
what was picked in case I want to reverse something later."

Status: Record (copy). **Source of truth is the picks log in Jeremy's main
Claude Duet chat** until the overnight lanes write to this file directly. This
copy was last refreshed at 2026-10-28 08:25 UTC (3:25 AM CT). Refresh it
with each handoff update.

Rules:
- Nothing merges or deploys on a pick alone. A pick only lets a lane keep
  building; merging still needs green CI, a passed review and Jeremy's
  approvals in `HANDOFF.md` section 1.
- Every pick is reversible. To reverse one, tell the lane (or edit the branch
  or PR named), then mark the row "Reversed: yes (date, by whom)". Rows marked
  "(Jeremy chose)" are his decisions, not picks.

Format: Date and time (CT) | Lane | Ticket or PR | Question | Options | Pick | Why | Branch or PR it lives on | Reversed?

## Picks

- 10-27 9:42 PM | Clearing players and teams | JEG-1190 | How Compare a trade opens | A empty with Try an example / B labeled example / C as is | A (Jeremy chose) | his call | not built yet | no
- 10-27 9:50 PM | Main green | PR #1021 | Footer "Connect the tool" and Find intro links are 15 to 18 px tall on phones (under the 44 px rule) | A invisible 44x44 hit area / B taller footer link row on phones / C 44 px on every link on touch screens | A | follows the existing 44 px rule with no visible change | PR #1021 (app/v2/v2.css) | no
- 10-27 9:50 PM | Main green | PR #1021 | Basis default-path test compares against a frozen engine from before JEG-1121 | re-freeze the baseline from current main / retire the frozen-engine comparison | re-freeze | keeps the regression lock; the fixture README says to re-freeze after a deliberate value change | PR #1021 (tests/fixtures/baseline_main_771c3422) | no
- 10-27 9:47 PM | Clearing players and teams | JEG-1190 | Clearing Your roster on Waivers (shared with both Find a trade screens) | A clear everywhere with a message saying so and Undo / B confirm first then clear / C clear Waivers only | A | lighter than a confirm, matches Find a trade's Clear, keeps the one-roster rule | fe/jeg-1190-clear-everywhere | no
- 10-27 9:47 PM | Clearing players and teams | JEG-1190 | Clearing a whole pasted league on Find a trade: league-wide | A Clear league button that asks to confirm, with Undo / B Clear league with Undo only / C leave per-team only | A | it wipes every team at once, so one confirm is worth it; Undo still there | fe/jeg-1190-clear-everywhere | no
- 10-27 9:58 PM | Trade viability fix | JEG-1129 | Backup WR rule in the trade finder (min_wr_backups; USO needs 4 healthy WRs for a 3-WR lineup) blocks all 14 near-miss trades on USO | A keep at 1 / B lower to 0 (11 trades become workable; best is JSN + Keenan Allen for Kenneth Walker III + Makai Lemon, you +14.6, them +1.0, High) | A | he has exactly 4 WRs, so the rule guards a thin spot; no code change, and the tool already takes min_wr_backups per search | no change (main as is) | yes: 10-27 10:24 PM Jeremy said lower it to 0; default changed to 0 on be/jeg-1129-wr-backups
- 10-28 | Clearing players and teams | JEG-1190 | Wording of the Compare sample button | A "Try a sample trade" (approved PMM doc 3.3) / B "Try an example" | A | matches the copy he already approved | PR #1023 (draft, not merged) | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | What counts as stale | only the current week behind / any served week behind after Thu 12:00 CT | any served week N after Thursday 12:00 CT of N+1 (two weeks behind is always stale) | matches the ticket's wording | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | How check_weekly_freshness reports weeks | replace the dashboard's week rule / add a per-source report | add a warning-only per-source report, keep the existing rule | JEG-1163 tests pin the existing rule | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | Move the DISCOVERY_OVERDUE alarm to Thu 12:00 CT | move / leave | leave as is | it's a discovery alarm, not the stale flag; existing tests pin it | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | Watchdog calendar | New York / Central | keep Central | switching broke the week-calendar clock test | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | Health check state names | keep one_week_behind / current, lagging, stale, unknown | the new names | no page reads the old value | PR #1022 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | How to treat a week asked for that isn't served | one rule for all / bad input vs missing week | weeks outside 1 to 22 are invalid input; a real week with no values gets week_unavailable | tells a typo apart from a week not published yet | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | Error shape for an unavailable week | 404 / empty result / 400 with details | 400 with a code, the served weeks and the default week | the Claude and ChatGPT tools can show the message | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | Response fields | rename sources_included / keep it and add fields | keep sources_included, add week, default_week, weeks, missing_sources | doesn't break existing callers | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | Which tools take a week | the five named in the ticket / every pricing tool | every pricing tool | they share one schema | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | Where links' wk= is read | the site's link codec / the MCP server | the MCP server | PR #958 is editing the codec | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | When links carry wk= | always / only when a week was asked for | only when asked for | the default week moves on its own | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | Default week when no history exists | error / fall back to the calendar | fall back to the calendar | matches what the page does | PR #1024 | no
- 10-27 10:25 PM | Board run (week transition) | JEG-1179 | Test clock | none / environment override | DDF_TODAY override | mirrors TRADE_VALUE_TODAY | PR #1024 | no
- 10-27 11:29 PM | Board run (week transition) | JEG-1176 | Where the lag test writes the lagging state | rewrite the built site only / the source fixture then re-sync | source fixture then re-sync | each test rebuilds the site and would undo a site-only rewrite | PR #1027 | no
- 10-27 11:29 PM | Board run (week transition) | JEG-1176 | How to fake a lagging CBS in the test data | reuse the existing helper as is / re-index CBS against ESPN | re-index | otherwise unrelated checks fail on the fake data | PR #1027 | no
- 10-27 11:29 PM | Board run (week transition) | JEG-1176 | Which holds the served-week check uses | the saved data's holds / the holds the page saw | the page's | with the saved ones, the corrupted-CBS guard stopped catching anything; cbsros and razzball now get checked too | PR #1027 | no
- 10-27 11:58 PM | Board run | JEG-1187 | What bar makes a trade "Market supported" | A keep the noise floor (label stays at 0 on real data) / B any gain above 0.05 for them on the trade chart average / C half the noise floor | B | matches "the charts tell the other manager it's favorable" and the 10-26 call that dropped the same floor on your side; on real leagues it moves roughly 20 trades per team from Force to Market supported | PR #1030 | no
- 10-27 11:58 PM | Board run | JEG-1187 | Pin real-data label counts in a page test | add a page assertion / unit tests plus the measured table in the log | unit tests plus log | real counts move with each week's data, so a page assertion would fail on data drift | PR #1030 | no
- 10-28 1:25 AM | Board run | JEG-1189 | Bench groups the engine itself reports as unfunded | fail on them / count as 0 and print a notice | count as 0 and print | it's documented engine behaviour the page already shows; failing would turn main red on standard/14 FantasyPros QB; any unreported zero still fails | PR #1029 | no
- 10-28 1:25 AM | Board run | JEG-1189 | The page's own budget guard overlaps the new check | drop the page layer / keep it and switch the guard off in the mutation test | keep it, guard off in the mutation | shows the new check catches a bug even if the guard is loosened later | PR #1029 | no
- 10-28 1:25 AM | Board run | JEG-1189 | Which bug to simulate | change a source's total budget / shift 1% of bench budget to starters | the bench-to-starter shift | a total change is already caught at page load; the shift is the case only a bench check sees | PR #1029 | no
- 10-28 1:25 AM | Board run | JEG-1189 | How to cover lagging weeks | depend on PR #1027's helper / read the page's week views directly | read the views directly | no dependency on an unmerged PR | PR #1029 | no
- 10-28 1:29 AM | Board run | JEG-1123 | How many trades the assistant's text lists | every returned row / top 5 then "N more" / top 10 | top 5 then "N more" (all rows stay in the structured result) | the ticket asks for a short top-N summary; five fits a chat reply | follow-up PR (JEG-1123/1124) | no
- 10-28 1:29 AM | Board run | JEG-1123 | League-wide search default size | 25 / 10 | 10 | the ticket says the default is 10 or fewer | follow-up PR (JEG-1123/1124) | no
- 10-28 1:29 AM | Board run | JEG-1124 | Shortest player name accepted | any / 2 characters | 2 characters | a single letter can silently pick a player | follow-up PR (JEG-1123/1124) | no
- 10-28 1:50 AM | Board run | JEG-1123 | Cap the league "Package" text at 5 too | cap at 5 / list the whole package (up to 15) | cap at 5 | same rows-twice problem; every package offer stays in the structured result | PR #1032 | no
- 10-28 1:50 AM | Board run | JEG-1124 | Where the short-name check lives | inside the name parser / a wrapper in the tool layer | the tool layer | gives a clean error and keeps the parser plain | PR #1032 | no
- 10-28 1:50 AM | Board run | JEG-1124 | Check names inside a pasted ddf-state | check / don't | don't | those names come from the site, not typed by the assistant | PR #1032 | no
- 10-28 1:50 AM | Board run | JEG-1124 | Minimum length on the opponent team-name field | add / leave | leave | it's a team label, not a player name | PR #1032 | no
- 10-28 1:50 AM | Board run | JEG-1124 | Empty optional fields in make_state | reject "" / treat as left blank | treat as left blank | keeps how the tool already behaves when a field is empty | PR #1032 | no
- 10-28 1:50 AM | Board run | JEG-1123 | Size limits in the tests | about 10% over the new sizes / tighter | about 10% | room for small wording changes, still fails if full rows return to the text | PR #1032 | no
- 10-28 2:00 AM | Board run | JEG-1125 | Which even band to use, with the ticket on hold since your Oct 27 comment | A: Compare's 1 point or 3% everywhere / B: shows-as-0.0 everywhere / C: one shared definition, no numbers move | C | your hold comment comes after the option A note, so nothing that changes labels was built; A's effect was measured (finder trades 7241 to 8502, none dropped) | PR #1033 | no
- 10-28 2:00 AM | Board run | JEG-1125 | Where the shared definition lives | new file / trade.js / finder.js | trade.js, with a test-guarded copy in finder.js | the MCP function loads finder.js alone, so a new file would break it | PR #1033 | no
- 10-28 2:00 AM | Board run | JEG-1125 | Also unify the other 0.05 floors (waivers, opportunities, viability) | include / leave | leave | they aren't Compare or Find a trade's even rule; a follow-up ticket if wanted | PR #1033 | no
- 10-28 2:00 AM | Board run | JEG-1125 | Open a PR while the ticket is on hold | stop / draft PR | draft PR | it moves no numbers and isn't merged, so nothing is decided for you | PR #1033 | no
- 10-28 2:20 AM | Main green | JEG-1193 / PR #1035 | Reviewed chip clipped in the phone context strip | A wrap the strip on phones / B chip without a link on phones, link stays in Customize and on Targets / C drop the chip on phones | B | keeps JEG-1119's one-line row and the chip's meaning; the strip already clips every legend item on phones, so only the dead link changes; desktop keeps the link | PR #1035 (app/v2/v2.js, tests/test_v2_mobile_phase1_render.py), draft, not merged | no
- 10-28 2:10 AM | Board run | JEG-1155 | Was the week 17 cap deliberate | stop and ask / go with 18 | go with 18 | no reason recorded in the commit, its log or the methodology; 17 vs 18 changes no value | PR #1034 | no
- 10-28 2:10 AM | Board run | JEG-1155 | Where the one week limit lives | product-data.js / value-model.js / a new file | product-data.js | it already holds the 18 matched to the Python calendar | PR #1034 | no
- 10-28 2:10 AM | Board run | JEG-1155 | Widget behaviour if product data hasn't loaded | fall back to 18 / stop with an error | stop with an error | a fallback would be a second definition | PR #1034 | no
- 10-28 2:10 AM | Board run | JEG-1155 | The v2 "Data through week" stepper also stops at 17 | change it now / leave it and flag it | leave it and flag it | outside the ticket's files; only means the stepper can't reach week 18 | PR #1034 | no
- 10-28 3:25 AM | Board run | JEG-1102 / JEG-1130 | Next issue to pick up on the 3 AM check | JEG-1102 research post (High) / JEG-1130 PMM copy (Medium) | JEG-1130 | JEG-1102 is blocked by JEG-1138 and your naming decision on JEG-1081; JEG-1130's prerequisite PRs have merged | branch muse/jeg-1130-pmm-copy | no
- 10-28 3:25 AM | Board run | handoff | Where the routine's HANDOFF.md and picks-log refresh lives | on a feature branch / its own docs branch | own docs branch, draft PR #1036 | keeps docs out of code reviews; PR #1031 (main green) also edits the handoff | PR #1036 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Part 1 (PR #1008) already merged | redo all / continue with what's left | continue | part 1 already covered storage copy, meta and subtitles | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Edit v2.js, which many open PRs touch | edit / leave | leave | 7 open PRs touch it; strings it writes at runtime stay as they are for now | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Rename the series labels | Market and Projections / DDF Charted and Projected Value / leave | leave | the PMM doc names them two different ways; needs your call | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Rename nav labels and page titles | rename / leave | leave | the doc's open question on names is still open and JEG-1138/1139 rebuild those pages | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Undervalued and Overvalued in Your league | Buy and Sell / Bargain and Cash in / leave | "Buy (market underpays)" and "Sell (market overpays)" | the glossary retires the old words; the playful tags are still an open question | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Find a trade empty note says "or your whole league" | as written / adapt | "Paste in their roster and yours" | that page takes team pastes, not a whole league | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Glossary "really worth" vs the guard that bans it on Methodology | use it / drop "really" | drop "really" | keeps the existing guard and the meaning | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Emoji in empty states | include / omit | omit | no other screen uses emoji; the playful-lines question is open | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | Also edit modules.js and team-summary.js (not in the ticket's list) | touch / leave | touch, strings only | otherwise labels disagree on the same screen | PR #1037 | no
- 10-28 3:35 AM | Board run | JEG-1130 | "he may not have a value yet" | the doc's "he" / "the player" | the doc's "he" | it's the approved line | PR #1037 | no
