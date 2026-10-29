# Fieldnotes revision 3: Find a trade review brief (JEG-1209)

Claude continuation of the revision-2 Fieldnotes preview handed over in #1089 (`2c8931231ccd2bbeb4946ac031aee5ac655182f4`). The baseline files in `docs/design/jeg-1209-fieldnotes/` are unchanged; this folder and `preview/jeg-1209-fieldnotes/` add revision 3. Private review only: nothing is published, deployed or merged by this work.

Decision, 2026-10-29: Jeremy approved Fieldnotes with one change, then narrowed it: "I just didn't want text boxes for how my leaguemates trade, and set everyone to default initially." The Managers card follows that rule (see How leaguemates trade below), and it is part of the rollout handoffs. Every other input is as revision 3 had it.

## How leaguemates trade: no free text, default to start (Jeremy, 2026-10-29)

The Managers card has no text box. Its note became checkboxes saved in the same note field: Likes rookies, Wants draft picks, Win-now, Rebuilding, Slow to reply, Rarely trades; the Other leanings anchor says "tick which below". Ticked boxes lead the note and any text already in it stays after them word for word, shown as "Kept from an earlier note" (JEG-1250); a box that would push the note past its length limit is refused and says so, rather than cutting the earlier text. Every manager starts at the default profile: each anchor Not sure, confidence Not set, no box ticked, Won't trade off ("Not described yet."). `build.py` applies the note change to the pinned #1084 copy (`NO_FREE_TEXT`), and `checks.py` fails if the Managers card has a text box or any manager starts away from the default.

League paste, team name, the Buy & sell and Values searches and the read-only URL and copy boxes keep their text boxes. Revision 2's own Find a trade route opens the revision-3 page, so there is one finder to review.

## What to look at

Open `preview/jeg-1209-fieldnotes/index.html` (self-contained; or serve the repo root with `python3 -m http.server 8767 --bind 127.0.0.1` and open `/preview/jeg-1209-fieldnotes/index.html`). Review at 1280 and 390 px. Routes: `#finder` (the page), `#flow` (current vs proposed), `#handoffs`. The top nav and Explore rosters open the revision-2 routes in `revision2.html`, built next to the page. The dashed Review states bar swaps in Values loading, No league and Projections missing; it is not part of the design.

Screenshots and browser checks come from the `JEG-1209 Fieldnotes preview` workflow on the PR, as the `jeg1209-fieldnotes-r3-shots` artifact. Each file name carries the commit, route and width; `shots.json` lists them with the check results.

## What revision 3 adds

Revision 2 drew the finder with its own stand-ins. Revision 3 runs the real sibling components, unchanged, inside the Fieldnotes page:

| Piece | Source | In the preview |
|---|---|---|
| League status header, folded summary | JEG-1233, #1091 | `league-status.js` on the real workspace store: teams, players, your team, saved state; loading, empty and error states from the component itself |
| Opponents to include | JEG-1231, #1090 | `opponent-inclusion.js`: stable team ids, Select all, Clear means none, "won't trade" from Managers greys the box |
| Columns | JEG-1232, #1093 | One fixed order, value first, no picker (Jeremy, 2026-10-29: "Go with the fixed order value first."; reviewed #1093 `b7e076f8` removed the picker and saved order). Revision 2's outcome-first order; phone cards follow it |
| Managers, Trade ideas, Stretch offers | JEG-1217, #1084 | `manager-profiles-ui.js` and `manager-recs-ui.js` mount themselves as on the live page; Likely / Possible in the list, Long shot in Stretch offers |
| Our and their fit labels for Trade ideas | main `opportunities.js` | `ourFitOf` / `theirFitOf` read the fixture's own fit fields, as `league.js` does |

Copies sit in `preview/jeg-1209-fieldnotes/vendor/` with the commit and git blob of each in `MANIFEST.json`. `build.py --check` fails when a copy, the baseline or the built page drifts.

### Pins and inherited findings (JEG-1250)

| PR | Pinned | Status |
|---|---|---|
| #1090 JEG-1231 | `a5471429` | Repinned to the reviewed accessibility fix (count described with each box). |
| #1091 JEG-1233 | `571876f0` | Open: empty league with unavailable or full storage still promises saving; Undo reads as a file or link import (review 00895375). Owner fix pending, then repin. |
| #1093 JEG-1232 | not vendored | Picker and saved order removed by Jeremy's fixed-order decision; the hidden-column Reset finding is superseded. |
| #1084 JEG-1217 | `a1e62342` | Open: Trade ideas drop partial or unjudged roster warnings, blank card after hide and show, stale names or gains after a rename (review 9e681c74), capture findings (59c00401). Newer `b29aac31` (fixed tags) is unreviewed and drops an existing note on load, so the preview stays on `a1e62342` with its own lossless note patch. |

### Preview storage (JEG-1250)

`build.py` (`PREVIEW_STORAGE`) moves both stores to preview-only keys, `ddf.preview.jeg1209.workspaces` and `ddf.preview.jeg1209.managerProfiles`; the live `ddf.v2.workspaces` and `ddf.v2.managerProfiles` are never read or written. The sample league is written only when the preview has no league of its own, or on Reset preview. Filters and manager profiles survive reload, No league and back, and reload in No league. Review-state changes, Also show and Reset preview write their final text into one live region outside the rerendered controls, and focus stays on the control pressed.

The components read the live page's `--v2-*` / `--ddf-*` token names. The preview points those names at the revision-2 roles (`src/continuation.css`), so they draw in Fieldnotes without any change to their own files. JEG-1231 already follows revision 2. The JEG-1232 and JEG-1233 concept previews were built on the older `app/v2-concept/concept.css` palette because no Fieldnotes revision had been handed over then; their components need no change, only their concept pages would.

## Current flow vs proposed

Today: Your league card (paste and team list), Team summary, Trade opportunities in a fixed order led by package capture, row details.

Proposed: League status → Explore rosters (revision 2) → Trade preferences → Managers → Trade ideas (with Stretch offers) → Trade opportunities (outcomes first, one fixed order) → inline details. It is a workspace with editable stages, not a wizard; Filters and Columns stay beside the results on desktop and above them on phone.

Why: package capture can rise while the starting lineup falls. In the historical example the top row captures +13.7 while our DDF starters fall 13.7. Revision 2 put starter changes first; revision 3 keeps that and shows what JEG-1217 does with it: with today's own-fit rule, 1 of the 30 stored opportunities is a trade idea, because 29 lower our starters. The Trade ideas card says so in its own words ("Left out: 29 trades that aren't a gain for you").

## States covered

| State | What the reader sees |
|---|---|
| Loaded | Status line with counts and saved state; results with counts of opponents searched |
| Values loading | Status card in its loading state; results say values are loading; Trade ideas hidden |
| No league | Status "No league loaded yet"; results say to paste the league on a computer |
| Projections missing | Projection columns and detail figures say Unavailable, never 0 |
| Opponents cleared | "No opponents are included", with the count of stored results the filter hides and Include all |
| Preferences changed | Results dimmed with "Results are from the previous preferences"; nothing pretends to rerun |
| Open trade filtered out | Details close with an announcement; no orphan panel |

## Limits, unchanged from #1089

Historical Week 7 fixture (`tv-20261027-0014-1bdef712`), synthetic four-team league. Fit labels are the historical predicate, not the approved Natural-fit rule (the stricter rule is Codex's). No search runs; package size and backups only mark results out of date. No preseason draft ranks are in the fixture, so the draft anchor in Managers falls back to the trade charts and says so. The row detail panel is revision 2's, from fixture impacts. The JEG-1230 readout is planned for that panel in rollout; #1088 does not wire any route yet, so nothing in production draws it today. The shared and page-only preferences (JEG-1229, #1086) are likewise planned: the preview names them but does not run or share them. Both saved-team selectors (JEG-1219) belong to the one-team finder; on the whole-league page Your team follows the star.

## Rollout handoffs (after approval)

- JEG-1137 shell and league entry: tokens and type from revision 2, the League status header (JEG-1233), the shared and page-only preference labels (JEG-1229).
- JEG-1138 Compare: the row-detail readout (JEG-1230, planned; not wired yet) and value views, reused by targets.
- JEG-1139 targets and the league finder: Opponents to include (JEG-1231), fixed column order value first (JEG-1232), Managers and Trade ideas (JEG-1217: no text boxes for how leaguemates trade, the note as checkboxes, every manager at the default profile to start), outcome-first columns.
- JEG-1140 Settings and explanations: independent; common preference fields with JEG-1137.
- Values and the homepage AI path (revision 2) still need an owner: a scope line on JEG-1137 or their own tickets.

## Decisions for Jeremy, one at a time

1. Design language: approved with changes on 2026-10-29 (no text boxes for how leaguemates trade; everyone at default to start).
2. Values page and homepage AI path ownership: add them to JEG-1137's scope, or give each its own rollout ticket.
