# Contract QA report

Generated 2026-10-16 02:07 UTC by scripts/contract_qa_report.py. Do not edit; rerun the script.

**Result: FAIL** (46 of 49 live lines pass, 14 pending)

## Live lines

| ID | Result | Line / finding |
|---|---|---|
| CT-01 | pass | Give and Receive pickers, Swap, Clear, and a shareable link that carries the league settings. |
| CT-03 | pass | The verdict is by DDF Value: |
| CT-04 | pass | Each source gets a waterfall, all on one shared scale: give steps go down, receive steps go up, then the net. |
| CT-05 | pass | An example trade shows before any player is added |
| CT-06 | pass | On phones, the verdict bar stays on screen. |
| CT-07 | pass | Tiers are cut across all positions. |
| GL-01 | pass | The brand is "Data Driven Football" |
| GL-02 | pass | Every number is right at its source: |
| GL-03 | pass | Missing values: |
| GL-04 | pass | Status is never shown by colour alone |
| GL-05 | FAIL | freshness usatoday: stuck '⚠ Not updating', want prior with a warning; freshness cbs: stuck '⚠ Not updating', want unknown with a warning; freshness: no confirmed source says Current |
| GL-06 | pass | The Showing bar is one line: what is shown, a legend, and Customize. |
| GL-08 | pass | DDF is the core value everywhere |
| GL-09 | FAIL | Compare's Player values shown does not offer ['ddf_value_charts'] |
| GL-10 | pass | The reader's selection (series, DDF inputs, ranking) is remembered on this device. |
| GL-11 | pass | Changes to league settings are a draft until Apply |
| GL-12 | pass | The bench share shown is the share the engine actually priced |
| GL-13 | pass | On phones (390 px), no page scrolls sideways and every tab is usable. |
| GL-14 | pass | If the engine fails, the page shows a failure state, never stale or partial numbers. |
| GL-15 | pass | Rescaled trade charts keep each publisher's own ranking order |
| GL-16 | FAIL | Rank by did not switch to ddf_value_charts |
| GL-17 | pass | Every module can be expanded beyond its default size (Player values: JEG-483; the other pages: JEG-500, done). |
| GL-18 | pass | Every module can be collapsed with a chevron (JEG-500, done): |
| GL-20 | pass | Search finds every player in the active NFL universe, including unrostered and practice-squad players |
| HV-01 | pass | Explains each view and lists the engine's series by method |
| MF-01 | pass | The Manifesto tab is first in the nav and carries Jeremy's text verbatim, checked word for word against a repo |
| PV-01 | pass | The default view is DDF Value against the rescaled trade charts. |
| PV-02 | pass | A chart of trade value by rank |
| PV-03 | pass | Zooming the chart shows player names on the points |
| PV-05 | pass | An X rank brush and a Y value brush |
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
| RF-01 | pass | Defaults to DDF Value, with series grouped in the picker |
| TT-01 | pass | The headline explains the page: "Where the trade market is wrong this week". |
| TT-02 | pass | The Sell and Buy lists are both visible: top 5 each, expandable, side by side from 1280 px. |
| TT-03 | pass | "Our value" defaults to DDF Value, with a source count on each row. |
| TT-04 | pass | Each row shows the largest gap and which chart it's against |
| TT-05 | pass | Chart values are labelled "rescaled", with an ⓘ that explains the rescaling (GL-21) . |
| TT-06 | pass | A chart that is a week behind shows a "Wk N" badge wherever it appears: Trade targets, Player values and Compa |
| TT-07 | pass | A chart value at or below 0 is never a buy or sell target. |
| TT-08 | pass | Players with only one source are included and flagged "◐ 1 source". |

## Pending (to build)

| ID | Ticket | Ticket status | Line |
|---|---|---|---|
| CT-02 | JEG-505 | unknown | The headline answers two questions in plain words, each with a confidence level (High / Medium / Low) : |
| GL-07 | JEG-498 | unknown | Customize is on every page : |
| GL-09 | JEG-497 | unknown | Three DDF Value versions are available on every page: the blended DDF Value, DDF Value from trade charts only, |
| GL-19 | JEG-501 | unknown | On desktop, ⓘ buttons open on hover as well as on click |
| GL-20 | JEG-502 | unknown | Search finds every player in the active NFL universe, including unrostered and practice-squad players |
| GL-21 | JEG-510 | unknown | Publishers' trade charts, put on our point scale, are called "Trade charts (rescaled)" |
| GL-22 | JEG-498 | unknown | League options rank above weights |
| GL-23 | JEG-537 | unknown | The bench share is a readout, not a slider: "Bench share this week: QB x%, RB y%, WR z%, TE w%, from your leag |
| GL-24 | JEG-537 | unknown | Edit league includes: |
| PV-04 | JEG-503 | unknown | The chart marks where Starter turns to Bench and Bench turns to Waiver : |
| PV-06 | JEG-503 | unknown | Grabbing the middle of a range brush moves both ends together . |
| PV-07 | JEG-503 | unknown | Clicking a source name in the chart legend turns that series on or off, among the series picked in Customize . |
| TT-05 | JEG-510 | unknown | Chart values are labelled "rescaled", with an ⓘ that explains the rescaling (GL-21) . |
| TT-09 | JEG-504 | unknown | Market average : |
