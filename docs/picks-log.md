# Data Driven Football picks log (repo copy)

Decisions the Claude lanes made on Jeremy's behalf, so he can reverse any of
them. Jeremy, 2026-10-27 9:45 PM CT: "Yes, use your picks, and make a note of
what was picked in case I want to reverse something later."

Status: Record (copy). **Source of truth is the picks log in Jeremy's main
Claude Duet chat** until the overnight lanes write to this file directly. This
copy was taken from it at 2026-10-28 03:22 UTC (10:22 PM CT Oct 27). Refresh it
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
- 10-27 9:58 PM | Trade viability fix | JEG-1129 | Backup WR rule in the trade finder (min_wr_backups; USO needs 4 healthy WRs for a 3-WR lineup) blocks all 14 near-miss trades on USO | A keep at 1 / B lower to 0 (11 trades become workable) | A | he has exactly 4 WRs, so the rule guards a thin spot; no code change, and the tool already takes min_wr_backups per search | no change (main as is) | no
- 10-28 | Clearing players and teams | JEG-1190 | Wording of the Compare sample button | A "Try a sample trade" (approved PMM doc 3.3) / B "Try an example" | A | matches the copy he already approved | PR #1023 (draft, not merged) | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | What counts as stale | only the current week behind / any served week behind after Thu 12:00 CT | any served week N after Thursday 12:00 CT of N+1 (two weeks behind is always stale) | matches the ticket's wording | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | How check_weekly_freshness reports weeks | replace the dashboard's week rule / add a per-source report | add a warning-only per-source report, keep the existing rule | JEG-1163 tests pin the existing rule | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | Move the DISCOVERY_OVERDUE alarm to Thu 12:00 CT | move / leave | leave as is | it's a discovery alarm, not the stale flag; existing tests pin it | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | Watchdog calendar | New York / Central | keep Central | switching broke the week-calendar clock test | PR #1022 | no
- 10-27 10:20 PM | Board run (week transition) | JEG-1180 | Health check state names | keep one_week_behind / current, lagging, stale, unknown | the new names | no page reads the old value | PR #1022 | no
- 10-28 7:10 AM | Board stuck on week 7 | JEG-1194 | Where the stuck-chain alert goes | A one GitHub issue opened and closed by the chain / B a Linear issue / C a Supabase monitoring row only | A | GITHUB_TOKEN is already in the workflow and GitHub emails the owner; Linear needs a key the chain doesn't have; the monitoring row already existed and reached nobody | PR (be/jeg-1194-board-publish) | no
- 10-28 7:10 AM | Board stuck on week 7 | JEG-1194 | How a red on a newer stored save stops holding the live chart | A pulse stamps a scope and the hold flips its match / B drop such reds in the pulse / C hold only on the stored side in the chain | A | keeps the red visible and still holds a build from the bad save | PR (be/jeg-1194-board-publish) | no
