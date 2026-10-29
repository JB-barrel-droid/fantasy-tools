# JEG-1221: trade-page parity, glossary and UX acceptance review

Purpose: turn the JEG-1220 parity matrix (Codex, Linear comment 2026-10-29 01:24 UTC) into an implementation-ready review of what the three trade pages *say*: labels, help text, empty and unavailable states. It lists only new findings, recommended strings with their exact destination, and Given/When/Then acceptance cases. The JEG-1220 source audit stays authoritative for code inventory and slices; Codex keeps implementation, shared-file integration and release.

Status: Record (review, 2026-10-29). Copy and spec only: no application code, math, defaults, ranking or design changed. Natural fit, the JEG-1125 even band and any default stay Jeremy's decisions.

Pages: **Your-team finder** = Find a trade: your team (`app/v2/finder.js`). **League-wide finder** = Find a trade: league-wide (`app/v2/league.js`, `app/v2/opportunities.js`). **Compare** = Compare a trade (`app/v2/v2.js` Compare section, `app/v2/trade.js`, `app/v2/shell.html`).

## Evidence base

- Source: `main` at `021c5bfd` (2026-10-29 01:37 UTC), which includes merged #1069 (interactive trades and guardrails). `app/v2/` is identical to `bf117c5f`, the last successful Deploy dashboard run, so the live site should match this source.
- Contract: `docs/feature-contract.md` (mirror of Jeremy's Google Doc, v1.2), lines GL-03, GL-08, GL-21, GL-26, CT-02, CT-03 and CT-08.
- Pending wording, read only: #1037 (JEG-1130 PMM copy part 2, open draft), #1071 (JEG-1212 source framework, open draft), and the JEG-1130 description's "Final decisions" line. #1072 was read only for its file list (league.js lines 2/2); nothing here touches it.
- Line numbers are on `021c5bfd`. #1037 and #1071 will move some of them.

## 1. Terminology: current versus pending

This review does not choose among these. They are recorded so each recommended string below can be written once and swapped when the owner ticket lands.

| Concept | Current main (all three pages) | #1037 (JEG-1130 part 2) | JEG-1130 "Final decisions" | #1071 (JEG-1212) | Contract |
|---|---|---|---|---|---|
| Our adjusted value | DDF Value | DDF Value | DDF Charted Value | unchanged | GL-08, GL-26: DDF Value |
| Projection-based value | DDF Value (projections); "Projections" in finder chips and delta lines | Projections, "the alternate lens" | DDF Projected Value | unchanged | GL-26, CT-08: **DDF Projections** |
| Average of the four rescaled charts | Trade chart average; "Market" in finder chips; "market" in delta lines; "the trade chart average" in fit text | The market | The Market (labels capitalized, prose lowercase) | keeps "Trade chart average", now said to include FantasyCalc as an estimate | GL-26: Trade chart average |
| The rescaled publisher series | Trade charts (rescaled) | unchanged | not stated | Published charts (USA Today, FantasyPros, CBS) and Observed-trade estimates (FantasyCalc) | GL-21: Trade charts (rescaled) |

In the strings below, `{Market}` means today's "Trade chart average" and becomes the JEG-1130 name when its runtime slice ships. `{Projections}` means today's "DDF Value (projections)" likewise. Implement them as one shared constant per name, not literals per page.

Two pending conflicts the owners should settle before strings move:

- **T1.** #1037 rewrites the League-wide intro (league.js:1440) as "the market (at least three of the four trade charts) says the other manager breaks even or wins". JEG-1130 makes "the Market" the four-chart *average*. The listing rule is a chart *count*. After both land, "the market" would mean an average in one sentence and a count in the next. Keep the count sentence free of the Market name (string S2 below).
- **T2.** #1071 shows "Published charts" (three sources) while the trade pages keep "Trade chart average" (four, including FantasyCalc). A reader sees "charts" for two different sets. When JEG-1130 renames the average to the Market, the collision goes away; until then, don't add "Published charts" to any trade page.

**Settled definition.** Natural fit means the trade works for both sides, never one side only (Jeremy, 2026-10-29). Every page that says "Natural" must mean both sides.

## 2. Label map across the three pages

One row per user-facing concept. "Decides" says whether the concept decides listing, the label or the verdict on that page, or is display only.

| Concept | Your-team finder | League-wide finder | Compare | Same meaning? |
|---|---|---|---|---|
| Who wins on value | "DDF Value says you win" (listing rule); chips "DDF Value". Decides listing. | Same rule; "DDF Value capture" column. Decides listing and order. | Verdict "X: you win by N" by DDF Value; falls back to the picked series when DDF Value is not in Compare's sources (CT-03). Decides the verdict. | Yes, except Compare's contracted fallback. |
| Will they accept: chart count | "the available charts say the other manager breaks even or wins" (finder.js:2346); "at least 3 of 4 charts agree they break even or win" (finder.js:1791). Decides listing: at least `min(3, available charts)` (`MIN_CHARTS = 3`). | "at least three of the four trade charts" (league.js:1440); column "Charts fair"; filter "Min charts fair". Decides listing. | Not shown. (The "N of M charts have the other manager winning or even" line is in the retired headline, CT-02.) | Same rule, three names. |
| Will they accept: average | "Market supported" label: their `{Market}` change above 0.05 (FIT_TIPS). Decides label. | Same label; "Market perception: Edge". | Deal read "Does the market think you are winning?"; Even band max(1, 3% of average side) (CT-08). Decides the deal read. | Same series, different even bands: **JEG-1125, held.** |
| Fit label | Natural fit / Market supported / Force fit | Same labels in "Overall fit"; **"Our fit" column uses Natural / Partial / Force with a different meaning** (F1) | None. Deal read cells instead ("Value win at a fair market price", "DDF Value likes it. The market doesn't.") | Finders yes; Compare has no fit label (F9). |
| Projections | "Show projections"; delta line "(+3.9 projections, +2.1 market)"; headline subtitle "backed by the projections". Display only. | Column "Projections agree / disagree / level / unavailable". Display only. | Third deal-read net "Is the value backed by projected production?" Display only. | Yes. |
| Starters and bench | "Starters", "Bench subtotal", "Show lineup details" (DDF Value and `{Market}` tables) | "Best starting lineup in DDF Value / Trade chart average" | "best starting lineup in DDF Value" only; "Opens/Uses N roster/bench spots"; "Empty starting slots" | Same idea; Compare has DDF Value only (JEG-1220 slice 4). |
| Display basis | Chips always DDF Value plus `{Market}` | "Rank by:" DDF Value or Trade chart average; changes the team summary only | "Player values shown:" picks the displayed series | Different controls, each route-specific. Copy must say what they don't change (F6). |
| Player with no value | "Not evaluated" chip is K/DEF only; others "no value"; note "has no DDF Value and is left out, not counted as 0" | "Not in this week's values" (no engine row); "no value" | Roster list "not in values" for every unpriced player, K/DEF included; search "○ Not valued: No chart or projection prices this player." | Three wordings; Compare merges K/DEF with missing (F5). |
| Single-source DDF Value | **No tag** | **No tag** | "◐ 1 source" and "≈ estimated" tags | No: finders break GL-03 (F2). |
| Too few charts | "Fit not judged: not enough trade charts are available this week"; "Only N trade charts are available this week. Not enough charts to judge acceptance." | "No trade chart is available this week, so acceptance cannot be judged."; chip "Trade chart average (too few charts)" | "Not enough charts"; "N of 3 compared charts needed"; "Not compared: X, not available for this league." | Same state, four phrasings (F7). |
| Your side / their side | "Your roster" / "Their roster" | "Your team is X"; "Our fit" / "Their fit"; "Their team fit" | "You give" / "You receive"; pickers labelled "Your team" / "Their team" | "Our" means DDF elsewhere ("our value", "Our methodology"), so "Our fit" reads as DDF's fit (F1). |

## 3. Findings

Severity: **High** = a reader can draw the wrong conclusion about the same trade. **Medium** = inconsistent or misleading but recoverable. **Low** = polish. "UI only" = no math, default or ranking change.

**F1 (High, UI only). League-wide uses "Natural" for two different tests in one table.** `ourFitOf` (opportunities.js:33-36) labels *your side only* "natural" (total rises, starters hold, construction OK), "partial" or "force". league.js:1155 capitalizes it into the "Our fit" column and league.js:1188 prints "Our fit: natural · …". The Overall fit column and filter use "Natural fit", which needs *both* sides. A row can read "Our fit: Natural" and "Overall: Force fit". "Partial" appears nowhere else on the site. Fix: strings S5 and S6.

  Decision (Jeremy, 2026-10-29 01:59 UTC, on the D1 question): "Natural means both sides, not just 1 side". So the one-side "natural" in `ourFitOf` is a defect, not a wording choice: no one-side check may carry the word Natural. The fix belongs to Codex, who owns the stricter Natural fit rule. S5/S6 are the recommended labels for the one-side column; this review changes no code.

**F2 (High, UI only, contract GL-03). The finders never show "◐ 1 source" or "≈ estimated".** GL-03 sits under "Everywhere": a single-source DDF Value is shown with "◐ 1 source". Compare renders it through `appendLowConfidence` (v2.js:5359, 5648). finder.js, league.js, opportunities.js and team-summary.js have no reference to `ddfLowConfidence` or `appendLowConfidence`. The same player in the same trade is tagged on Compare and untagged on both finders. Fix: render the existing tag next to the DDF Value chip (league.js:113, finder.js chip builder) and in the "Target:" line (finder.js:1981). Reuse the v2.js helper; no new rule.

**F3 (High, UI only). The listing rule and the "Market supported" rule are different tests, and no page says so.** Both finders list a trade when DDF Value says you win and at least 3 charts are fair to them, or every available chart when fewer than 3 are available (`judgeSums`, finder.js:65-81; `minCharts = min(3, available charts)`, finder.js:162). "Market supported" uses the `{Market}` *average* (finder.js:873). So a listed trade can be a Force fit with "The trade charts do not favor them". The intros (finder.js:2346, league.js:1440) describe only the count rule, and the Your-team intro says "the available charts" with no number. Fix: S1, S2 and S3 state the count, and the Market supported tip says it uses the average.

**F4 (Medium, UI only). "Min charts fair" offers values that can't filter anything.** league.js:1051 offers Any, 1, 2, 3, 4. The search already drops trades below `min(3, available charts)` fair charts (finder.js:162, :191). With 3 or more charts available, Any, 1, 2 and 3 return the same list and only 4 narrows it. Fix: S7. Saved workspaces holding 0, 1 or 2 read as the floor. That is a no-op, not a default change.

**F5 (Medium, UI only, contract GL-03). Missing-value states use three wordings, and Compare merges two states.** K/DEF are "Not evaluated" by design. A player missing from this week's values is a data gap. finder.js:1652 and league.js:107 keep them apart. Compare's loaded-roster list (v2.js:5147) prints "not in values" for both, and "no value" for a priced player missing in the shown series. GL-03 asks for the reason with every null. Fix: S8, S9 and S10. The same three states and words on every page.

**F6 (Medium, UI only). Display controls don't say what they leave alone.**
- Compare: "Pick a series in Player values shown." (v2.js:5958) reads as if the picker chooses the verdict. Per CT-03 the verdict stays on DDF Value while DDF Value is among Compare's sources, and follows the picked series only when DDF Value is hidden (v2.js:5261). Fix: S11.
- League-wide "Rank by:" (league.js:773) changes the team summary and its filters only. Opportunities stay ranked by fit, then DDF Value capture. Fix: S12.

**F7 (High, UI only). With 1 or 2 charts, the League-wide finder says nothing, and both intros become false.** With fewer than 3 charts the finders still search, on every available chart (`min(3, n)`), and leave fit unjudged. The Your-team finder warns ("Only 2 trade charts are available this week. Not enough charts to judge acceptance.", finder.js:1769). The League-wide finder warns only at 0 charts (league.js:1069), so with 1 or 2 it lists trades under an intro that says "at least three of the four". Compare's deal read needs 3 (`MIN_DEAL_CHARTS`, trade.js:291) and says "N of 3 compared charts needed". Same state, four phrasings, one page silent. Fix: S13 on all three pages, with the count, including League-wide at 1 or 2 charts. No threshold changes.

**F8 (Medium, UI only). Compare points to a page that doesn't exist.** v2.js:5118 and v2.js:5172 say "Add two rosters in Your league…" / "Add both rosters in Your league…". The nav has "Find a trade: league-wide" and an "Edit league" button, and no "Your league". Fix: S14.

**F9 (Medium, decision D1). The fit label is lost on "Open in Compare a trade".** finder.js:1976 and league.js:894 open the trade in Compare, which shows a deal read and no fit label. A reader who opened "Natural fit · High viability" can land on "DDF Value likes it. The market doesn't." with nothing linking the two. The two can legitimately differ: the label checks rosters with a 0.05 band, the deal read uses max(1, 3%) (JEG-1125, held). Options in D1.

**F10 (Low, UI only). The finder names the market view four ways on one card.** Chips say "Market" (chipTooltip, finder.js:846); the delta line says "+2.1 market" (deltaLine, finder.js:852); the fit text says "the trade chart average" (VIEW_NAME, finder.js:773); the lineup table says "Trade chart average" (VIEW_LABEL, finder.js:1871). The projections view is named "projections", "Projections" and "DDF Value (projections)" the same way. Fix: one `{Market}` and one `{Projections}` constant in finder.js, used by chips, delta lines, fit text and tables. This also makes the JEG-1130 swap a two-line change.

**F11 (Low, UI only). Duplicate team names can't be told apart.** Names aren't unique (workspace.js:125 `renameTeam`, :116 `addTeam`). Compare's pickers show `${name} (${count})` (v2.js:5049); the League-wide opponent filter shows the bare name (league.js:1048); a league re-paste matches teams by name (league.js:630, `byName`), so two same-named pasted teams resolve to one saved id. The paste merge is a behaviour bug for JEG-1219 (saved-team picker), not copy; the label fix is S15. Not browser-verified.

**F12 (Low, contract wording). The contract's projection name differs from the code.** GL-26 and CT-08 say "DDF Projections"; the code says "DDF Value (projections)"; JEG-1130 says "DDF Projected Value". The contract says to ask Jeremy before changing a line, so this is D2.

Checked and not a finding: package size labels match across the finders ("Up to N-for-N"; only the Your-team finder offers "1-for-1 only"), and Compare carries no discovery filter. The Your-team finder already says "Larger package than searched" when an edited trade outgrows the search (finder.js:2015). The finders' default package and keep-starters flags differ; JEG-1220 already lists them as default decisions.

## 4. Recommended strings (before and after)

Copy only, current terminology with `{Market}`/`{Projections}` tokens. Destinations are on `021c5bfd`.

| ID | Destination | Before | After | Finding |
|---|---|---|---|---|
| S1 | finder.js:2346 (Your-team intro) | Lists trades where DDF Value says you win and the available charts say the other manager breaks even or wins. | Lists trades you win on DDF Value where at least 3 trade charts (or every available chart, when fewer are available) say the other manager breaks even or wins. Each trade is then labelled Natural fit, Market supported or Force fit. | F3 |
| S2 | league.js:1440 (League-wide intro; #1037 also edits it, see T1) | Your team against every other team. Each trade is one you win on DDF Value while at least three of the four trade charts say the other manager breaks even or wins. Ranked by fit first, then by DDF Value capture. | Your team against every other team. Each trade is one you win on DDF Value while at least 3 trade charts (or every available chart, when fewer are available) say the other manager breaks even or wins. Ranked by fit first, then by DDF Value capture. | F3, T1 |
| S3 | finder.js:873 FIT_TIPS.market, used by both finders | Market supported: their Trade chart average fit value rises by more than 0.05 points, using the league's bench share. A trade can earn this label while their starters lose value or either roster has construction issues; check the team-fit details. | Market supported: their `{Market}` rises by more than 0.05 points, using the league's bench share. This uses the average of the charts, not the chart count that put the trade on the list. A trade can earn this label while their starters lose value or either roster has construction issues; check the team-fit details. | F3 |
| S4 | finder.js:1791 (no-results note) | No trade found where DDF Value says you win and at least 3 of 4 charts agree they break even or win. Try a larger package. | Keep #1037's version. Change only "charts agree they break even or win" to "charts say they break even or win", so the word "agree" stays with projections. | F3 |
| S5 | opportunities.js:33-36 `ourFitOf` labels, shown at league.js:1155 and :1188 | natural / partial / force | works / gains, roster issue / doesn't work (never "natural": Jeremy, 2026-10-29, Natural means both sides) | F1 |
| S6 | league.js:1188 detail line and the column header | Our fit: … · Their fit: … ; "Their team fit" | Your side: … · Their side: … ; header "Their side" | F1 |
| S7 | league.js:1051 filter | Min charts fair: Any, 1, 2, 3, 4 | Charts fair to them: Every listed trade, All 4. Hide the control when fewer than 4 charts are available. | F4 |
| S8 | every page, K/DEF | Not evaluated / Kept, not evaluated (no value for defenses and kickers) / not in values | Not evaluated: kickers and defenses have no trade value. Kept on the roster, left out of every sum. | F5 |
| S9 | every page, no engine row | Not in this week's values / not in values / missing from this week's values | No value this week: not in this week's sources. Left out of every sum, not counted as 0. | F5 |
| S10 | every page, priced but missing in the shown series | no value | No `{series}` value: left out of this series, not counted as 0. | F5 |
| S11 | v2.js:5958 | Pick a series in Player values shown. | Pick a series in Player values shown. The verdict reads DDF Value whenever it is one of Compare's sources. | F6 |
| S12 | league.js:773, help under "Rank by:" | (none) | Orders the team summary only. Trade opportunities are always ranked by fit, then by DDF Value capture. | F6 |
| S13 | finder.js:838, :1768, :1769; league.js:1069 (and a new League-wide note at 1 or 2 charts); league.js:112 chip | Fit not judged: not enough trade charts are available this week / No trade chart is available this week, so acceptance cannot be judged. / Trade chart average (too few charts) | Not enough trade charts this week ({n} of 3 needed), so we can't judge whether they'd accept. Chip: `{Market}` unavailable ({n} of 3 charts). | F7 |
| S14 | v2.js:5118, v2.js:5172 | Add two rosters in Your league to see … | Add two teams under Find a trade: league-wide to see … | F8 |
| S15 | v2.js:5049, league.js:1048 | `Team 1 (14)` / `Team 1` | When two teams share a name, add the saved position: `Team 1 (14 players) · team 3 of 12`. Unique names stay as they are. | F11 |

## 5. Acceptance cases (Given / When / Then)

Run each in Standard, Half PPR and PPR at 12 teams unless the case says otherwise. "Same" means equal to 0.1 point as rendered.

**AC1. One identical explicit trade across all three pages.**
Given a saved league with my team A (starred) and team B, and a trade T (A gives X, receives Y) that the Your-team finder lists for A vs B,
When T is opened on the League-wide finder (opponent filter B) and in Compare with A and B loaded (via "Open in Compare a trade" and also by picking X and Y by hand),
Then the DDF Value net, the `{Market}` net and both teams' starter before/after values are the same on all three pages; both finders show the same fit label and the same "◐ 1 source" / "≈ estimated" tags; Compare's verdict says it reads DDF Value; and the by-hand Compare result equals the opened one.

**AC2. Too few charts.**
Given only 2 trade charts have values this week,
When each page loads A vs B,
Then both finders show S13 with "2 of 3 needed" above any trades they list, and show no fit label; the League-wide intro no longer claims three charts; Compare shows its deal-read unavailable state with the same count; no page shows 0 in place of the missing average.

**AC3. A held or unavailable source.**
Given FantasyCalc is unavailable (held) and the three other charts have values,
When each page loads,
Then the finders count "3 of 3" charts and say so; Compare lists FantasyCalc under "Not compared: …, not available for this league."; no page shows the held source's value as 0; data from a previous season is labelled previous-season, never shown as this season.

**AC4. Player states.**
Given A's roster holds a kicker, a player with no engine row, and a player priced by DDF Value but missing in the series shown on Compare,
When each page shows A,
Then all three pages show S8, S9 and S10 respectively, with the same words, and none of the three counts toward any sum.

**AC5. Single-source DDF Value.**
Given Y's DDF Value rests on one source,
When T appears on each page,
Then "◐ 1 source" with the engine's note sits beside Y's DDF Value on both finders and on Compare (GL-03).

**AC6. Duplicate team names.**
Given two saved teams both named "Team 1" with different rosters,
When the reader opens Compare's team pickers, the League-wide opponent filter and the League-wide paste,
Then the two are told apart by S15; choosing one, renaming it and coming back keeps the same team (by saved id, not name); re-pasting the league keeps two teams (coordinate with JEG-1219, which owns the store change).

**AC7. No roster.**
Given A is starred and B has no players,
When each page loads,
Then the Your-team finder asks for a trade partner (#1037 string), the League-wide finder says a team with no roster was skipped, Compare shows S14, and no page shows a fit label, a verdict or a 0 total for B.

**AC8. Display basis versus decision basis.**
Given DDF Value is among Compare's sources and "Player values shown" is set to another series,
When a trade is entered,
Then the verdict still reads DDF Value and the page says so (S11). Given DDF Value is removed from Compare's sources, Then the verdict reads the picked series and names it (CT-03). Given League-wide "Rank by" is set to `{Market}`, Then the team summary reorders and the opportunity order does not (S12).

**AC9. Explicit deal versus discovery.**
Given Compare is open,
Then it shows no package-size, fit, opponent, capture or charts-fair filter. Given a Your-team finder trade is edited past the searched package size, Then the card shows its "Larger package than searched" note, and the same trade in Compare gives the same numbers with no such note.

**AC10. Reader comprehension of starter, bench, market and projection data.**
Given trade T gains A's starters and costs A's bench on DDF Value, and projections disagree,
When a reader looks only at the visible text of T's card or readout (no tooltips) on each page,
Then they can answer from that text: (1) which value decided whether T is listed or how it is called, (2) whether A's starters improve, (3) whether A's bench gets worse, (4) whether the market agrees, (5) whether projections agree. Check it with a rendered-text test that finds each answer phrase, plus a five-reader check where at least 4 of 5 answer all five correctly.

## 6. Decisions for Jeremy

**D1. When a finder trade opens in Compare, what links its fit label to Compare's read?**
- A. Compare shows one line, only when opened from a finder: "Find a trade labelled this Market supported." The label is recomputed from the same rosters, no new math.
- B. Compare shows a fixed note under the deal read: "Find a trade also checks both rosters' starting lineups, so its fit label can differ from this read."
- C. Change nothing until Natural fit and the JEG-1125 even band are settled.

Recommended: **B**. It's copy only, true under any outcome of the held Natural fit and even-band decisions, and it doesn't put a disputed label on a new page.

Status 2026-10-29: Jeremy answered this question with the definition "Natural means both sides, not just 1 side" (recorded under F1). That settles the term. Logged pick (coordinator, picks log 2026-10-28 9:01 PM CT, reversible): **C**, no note or carry-over now. Caveat: Compare's deal read keeps its own even band (CT-08, JEG-1125 held), so a finder label and Compare's read can still differ; revisit D1 when JEG-1125 is settled.

**D2. Which name does the contract use for the projections view on the trade pages?** The contract (GL-26, CT-08) says "DDF Projections", the code says "DDF Value (projections)", and JEG-1130's final decisions say "DDF Projected Value".
- A. Use "DDF Projected Value" and update GL-26 and CT-08 when JEG-1130's runtime slice ships.
- B. Keep the contract's "DDF Projections" and change the code to it.
- C. Keep "DDF Value (projections)" and update the contract to match the code.

Recommended: **A**, since JEG-1130 records it as final; the contract line changes with your yes, in the same PR.

## 7. Evidence gaps

- No browser QA. This environment can't load the live site (the proxy refuses github.io; a fetch returned an older cached build tag, `tv-20261028-0141-abc4675`). The live state is inferred from the last successful Deploy dashboard run on `bf117c5f`, whose `app/v2/` matches the source reviewed.
- F11's paste merge is read from code (league.js:617-630), not reproduced.
- The JEG-1130 PMM Google Doc wasn't opened; JEG-1130's description and #1037's diff stand in for it.
- #1037 and #1071 are open drafts; their strings may change before merge.
