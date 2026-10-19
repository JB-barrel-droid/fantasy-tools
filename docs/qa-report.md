# Contract QA report

Generated 2026-10-19 18:01 UTC by scripts/contract_qa_report.py. Do not edit; rerun the script.

**Result: PASS** (75 of 75 live lines pass, 9 pending)

## Live lines

| ID | Result | Line / finding |
|---|---|---|
| CT-01 | pass | Give and Receive pickers, Swap, Clear, and a shareable link that carries the league settings. |
| CT-02 | pass | The headline answers two questions in plain words, each with a confidence level (High / Medium / Low) : |
| CT-03 | pass | The verdict is by DDF Value: |
| CT-04 | pass | Each source gets a waterfall, all on one shared scale: give steps go down, receive steps go up, then the net. |
| CT-05 | pass | An example trade shows before any player is added |
| CT-06 | pass | On phones, the verdict bar stays on screen. |
| CT-07 | pass | Tiers are cut across all positions. |
| CT-08 | pass | A rule-based deal read replaces "The sources split." It is driven by logic, never a language model |
| GL-01 | pass | The brand is "Data Driven Football" |
| GL-02 | pass | Every number is right at its source: |
| GL-03 | pass | Missing values: |
| GL-04 | pass | Status is never shown by colour alone |
| GL-05 | pass | Freshness: |
| GL-06 | pass | The Showing bar is one line: what is shown, a legend, and Customize. |
| GL-07 | pass | Customize is on every page : |
| GL-08 | pass | DDF is the core value everywhere |
| GL-09 | pass | Three DDF Value versions are available on every page: the blended DDF Value, DDF Value from trade charts only, |
| GL-10 | pass | The reader's selection (series, DDF inputs, ranking) is remembered on this device. |
| GL-11 | pass | Changes to league settings are a draft until Apply |
| GL-12 | pass | The bench share shown is the one the engine computed from the reader's settings (the readout in GL-23) or, whe |
| GL-13 | pass | On phones (390 px), no page scrolls sideways and every tab is usable. |
| GL-14 | pass | If the engine fails, the page shows a failure state, never stale or partial numbers. |
| GL-15 | pass | Rescaled trade charts keep each publisher's own ranking order |
| GL-16 | pass | Tier (Starter / Bench / Waiver) follows the ranking series in use, which is DDF Value by default. |
| GL-17 | pass | Every module can be expanded beyond its default size (Player values: JEG-483; the other pages: JEG-500, done). |
| GL-18 | pass | Every module can be collapsed with a chevron (JEG-500, done): |
| GL-19 | pass | On desktop, ⓘ buttons open on hover as well as on click |
| GL-20 | pass | Search finds every player in the active NFL universe, including unrostered and practice-squad players |
| GL-21 | pass | Publishers' trade charts, put on our point scale, are called "Trade charts (rescaled)" |
| GL-22 | pass | League options rank above weights |
| GL-23 | pass | The bench share is a readout, not a slider: "Bench share this week: QB x%, RB y%, WR z%, TE w%, from your leag |
| GL-24 | pass | Edit league includes: |
| GL-25 | pass | A source that disagrees with the other sources more than usual shows a small "Check" chip next to its name, in |
| GL-26 | pass | Our names are defined once and shown wherever they appear, with an info button: DDF Value is fair value, the p |
| GL-27 | pass | Every source name is a link to that publisher's page for the served week, opening in a new tab (the addresses  |
| GL-28 | pass | The default league is 12 teams, PPR, 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K / 1 DEF with 7 bench slots |
| HV-01 | pass | Explains each view and lists the engine's series by method |
| HV-02 | pass | How values work leads with the three numbers (DDF Value, DDF Projections, Trade chart average) and "Where the  |
| MF-01 | pass | The Manifesto tab is first in the nav and carries Jeremy's text verbatim, checked word for word against a repo |
| PV-01 | pass | The default view is DDF Value against the rescaled trade charts. |
| PV-02 | pass | A chart of trade value by rank |
| PV-03 | pass | Zooming the chart shows player names on the points |
| PV-04 | pass | The chart marks where Starter turns to Bench and Bench turns to Waiver (JEG-503; pinned by `tests/test_v2_char |
| PV-05 | pass | An X rank brush and a Y value brush |
| PV-06 | pass | Grabbing the middle of a range brush moves both ends together, keeping the width; Shift+arrow on the fill does |
| PV-07 | pass | Clicking a source name in the chart legend turns that series on or off, among the series picked in Customize;  |
| PV-08 | pass | One toolbar: Search · Position · Show · Rank by · Δ Prior week · More · Reset. |
| PV-09 | pass | Reset restores everything, including Rank by. |
| PV-10 | pass | The table follows Show |
| PV-11 | pass | A heat tint shows whether each value is above or below the ranking value |
| PV-12 | pass | Clicking a row opens the player detail: all sources, by method. |
| PV-13 | pass | Δ Prior week shows each value's change since last week |
| PV-14 | pass | Expand the chart to full screen (JEG-483). |
| PV-15 | pass | Expand the table to full height, with Pos / Team / Tier sortable (JEG-483). |
| PV-16 | pass | A Reset zoom link appears while zoomed and clears both brushes (JEG-483). |
| PV-17 | pass | Active filter chips, each clearing one filter (JEG-483). |
| PV-18 | pass | The chart's Y axis follows the top and bottom visible points (values of 0 ignored), with about 4% padding and  |
| PV-19 | pass | A player that no shown series (DDF Value included) prices above 0 is hidden, with a note saying how many; a se |
| PV-20 | pass | Rank by always offers the DDF weighted projections (ESPN, CBS rest of season, Razzball) as well as the three D |
| RF-01 | pass | Defaults to DDF Value, with series grouped in the picker |
| RF-02 | pass | "Where the market and the projections disagree": compares the change in Trade chart average with the change in |
| RS-01 | pass | A Research tab follows How values work and routes at `#research`: an index of the published posts, each with t |
| RS-02 | pass | Every published post was approved by Jeremy as a Google Doc before its `published` flag was set |
| RS-03 | pass | Live widgets in a post read the engine, and a what-if never changes the reader's saved league settings until t |
| TT-01 | pass | The headline explains the page: "Where the trade market is wrong this week". |
| TT-02 | pass | The Sell and Buy lists are both visible: top 5 each, expandable, side by side from 1280 px. |
| TT-03 | pass | "Our value" defaults to DDF Value, the blend (Jeremy, 2026-10-16: DDF decides who we want and don't want; this |
| TT-04 | pass | Check 1 ranks by the market consensus: the median of the INDEXED trade charts (the rescaled series, not the ad |
| TT-05 | pass | Chart values are labelled "rescaled", with an ⓘ that explains the rescaling (GL-21) . |
| TT-06 | pass | A chart that is a week behind shows a "Wk N" badge wherever it appears: Trade targets, Player values and Compa |
| TT-07 | pass | A chart value at or below 0 is never a buy or sell target. |
| TT-08 | pass | Players whose DDF Value rests on only one source are included and flagged "◐ 1 source" |
| TT-10 | pass | The page runs two numbered checks, and the subtitle names both: "1 |
| TT-11 | pass | Check 2 compares DDF Value with the trade-chart consensus (median of 2+ charts) and with each chart, by positi |
| TT-12 | pass | Hovering, focusing or tapping a chart value on Trade targets shows where it comes from, leading with the numbe |

## Pending (to build)

Shipped check: the partial check of what is already built (also listed above); 'none' means no check exists yet. The line goes live when the Doc drops "to build".

| ID | Ticket | Ticket status | Shipped check | Line |
|---|---|---|---|---|
| CT-02 | JEG-505 | Done | pass | The headline answers two questions in plain words, each with a confidence level (High / Medium / Low) : |
| GL-07 | JEG-498 | Done | pass | Customize is on every page : |
| GL-09 | JEG-497 | Done | pass | Three DDF Value versions are available on every page: the blended DDF Value, DDF Value from trade charts only, |
| GL-19 | JEG-501 | Done | pass | On desktop, ⓘ buttons open on hover as well as on click |
| GL-20 | JEG-502 | Done | pass | Search finds every player in the active NFL universe, including unrostered and practice-squad players |
| GL-21 | JEG-510 | Done | pass | Publishers' trade charts, put on our point scale, are called "Trade charts (rescaled)" |
| GL-22 | JEG-498 | Done | pass | League options rank above weights |
| TT-05 | JEG-510 | Done | pass | Chart values are labelled "rescaled", with an ⓘ that explains the rescaling (GL-21) . |
| TT-09 | JEG-504 | Done | none | Market average : |
