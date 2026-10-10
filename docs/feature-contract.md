<!--
Mirror of the Google Doc (source of truth): https://docs.google.com/document/d/1UDRlVTdOiAdI6gSSklxwB-R9uINozVmIILMwbvCBiH0. Regenerate when the Doc changes; never edit this file to change the contract.
Regenerate: python scripts/sync_feature_contract.py <exported text>. Mirrored 2026-10-09.
tests/test_v2_contract_render.py reads every **XX-NN** ID below.
-->

# Data Driven Football: feature contract

**This doc is the source of truth for what the site must keep doing** (Jeremy, 2026-10-09).

A change that breaks a line does not ship. To change or remove a line, ask Jeremy first, then record his decision and the date under that line.

Each line has an ID. One contract test (tests/test_v2_contract_render.py, JEG-506) quick-checks every ID: the feature is present and its basic behaviour works. Deeper correctness tests live elsewhere. A line marked *(to build: JEG-xxx)* is agreed but not live yet; the test checks it once it ships.

Status: v1.1 (2026-10-09). Earlier versions are superseded.

## Everywhere (GL)

  - **GL-01** The brand is "Data Driven Football". "Vegas" never appears. "VORP" appears only as "VORP vs waivers".

  - **GL-02** Every number is right at its source:

  - Engine values equal the engine.
  - Values that exist only on the front end are computed in v2 from engine values, then tested against an independent calculation. Examples: averages, gaps, trade nets, confidence.
  - (Jeremy, 2026-10-09: "There are some values that are only calculated on the front end, in which case math must be done there.")

  - **GL-03** Missing values:

  - A player missing from a fully loaded chart is worth 0, shown as "0.0".
  - "—" appears only when the engine returns null, always with its reason.
  - A DDF Value from a single source is shown with a "◐ 1 source" tag; the tooltip explains it.

  - **GL-04** Status is never shown by colour alone. It always pairs a symbol with a word.

  - **GL-05** Freshness:

  - "Current" means the source has published the current football week.
  - The header chip says Current only for sources confirmed on the current football week.
  - Sources a week behind, not updating, or of unknown freshness show a warning.

  - **GL-06** The Showing bar is one line: what is shown, a legend, and Customize.

  - **GL-07** Customize is on every page *(to build: JEG-498)*:

  - It lists every available dataset, grouped as: DDF Value (three versions and their inputs), Projections, Trade charts (adjusted), Trade charts (rescaled), and Advanced value above waivers.
  - Each group has Select all / none. The panel has Reset to default and Done / Cancel.
  - Each page sets its own defaults to suit its objective.

  - **GL-08** DDF is the core value everywhere. ESPN is one input, not the anchor. Defaults, tiers and wording use DDF Value.

  - (Jeremy, 2026-10-09: "ESPN is no longer the core weight, it is DDF".)
  - Moving the rescaling anchor to DDF is JEG-499. It is on hold while the back end confirms the anchor with Jeremy.
  - The source-neutral pipeline redesign (JEG-508) will update this section.

  - **GL-09** Three DDF Value versions are available on every page *(to build: JEG-497)*:

  - the blended DDF Value;
  - DDF Value from trade charts only;
  - DDF Value from player projections only.

Each is one number per player, the same on every tab and view. Each is the equal-weight mean of adjusted values only. (Jeremy, 2026-10-09.)

  - **GL-10** The reader's selection (series, DDF inputs, ranking) is remembered on this device.

  - **GL-11** League options rank above weights: Edit league is the primary control, and Weights & bench is secondary when shown together. Edits are a draft until Apply. (Jeremy, 2026-10-09; JEG-498.)

  - **GL-12** The bench share shown is the share the engine actually priced. A floor is noted.

  - **GL-13** On phones (390 px), no page scrolls sideways and every tab is usable.

  - **GL-14** If the engine fails, the page shows a failure state, never stale or partial numbers.

  - **GL-15** Rescaled trade charts keep each publisher's own ranking order. A guard checks this on every build (JEG-482).

  - **GL-16** Tier (Starter / Bench / Waiver) follows the ranking series in use, which is DDF Value by default.

  - **GL-17** Every module can be expanded beyond its default size *(to build: JEG-483 for Player values, JEG-500 for the other pages)*.

  - **GL-18** Every module can be collapsed with a chevron *(to build: JEG-500)*:

  - Collapsed, it shows its title and a one-line summary, so nothing gets lost.
  - The state is remembered on this device.

  - **GL-19** On desktop, ⓘ buttons open on hover as well as on click. They stay keyboard- and touch-accessible *(to build: JEG-501)*.

  - **GL-20** Search finds every player in the active NFL universe, including unrostered and practice-squad players. A player with no value shows "0.0" and the reason, and always appears. *(to build: JEG-502)*

  - (Jeremy: "The user knowing they are a 0 is better than the user questioning why they aren't in the tool.")

  - **GL-21** Publishers' trade charts, put on our point scale, are called **"Trade charts (rescaled)"**. Never use "as published" or a bare "indexed" as a label. One-line meaning: "Each publisher's trade values, rescaled to our point scale for your league; their ranking order is unchanged." *(to build: JEG-510)*

  - (Jeremy, 2026-10-09: "anywhere we are saying 'as published' we are really saying indexing what was published; so sort out copy… else it may confuse the reader.")

## Manifesto (MF)

  - **MF-01** The Manifesto tab is first in the nav and carries Jeremy's text verbatim. The landing tab stays Trade targets *(JEG-494)*.

## Player values (PV)

  - **PV-01** The default view is DDF Value against the rescaled trade charts.
  - **PV-02** A chart of trade value by rank. The DDF Value line is drawn on top and heavier than the others.
  - **PV-03** Zooming the chart shows player names on the points. (Jeremy, 2026-10-08: "I like the feature when you zoom in on the chart you see the names.")
  - **PV-04** The chart marks where Starter turns to Bench and Bench turns to Waiver *(to build: JEG-503)*:

      - vertical lines at each break;
      - "Starter", "Bench" and "Waiver" across the top of the chart area, centred in their sections, in light grey;
      - across positions, each line sits where the break really falls (some bench WRs and RBs outvalue starting QBs).
  - **PV-05** An X rank brush and a Y value brush. Dragging either one updates Show and the table.
  - **PV-06** Grabbing the middle of a range brush moves both ends together *(to build: JEG-503)*.
  - **PV-07** Clicking a source name in the chart legend turns that series on or off, among the series picked in Customize *(to build: JEG-503)*.
  - **PV-08** One toolbar: Search · Position · Show · Rank by · Δ Prior week · More · Reset.
  - **PV-09** Reset restores everything, including Rank by.
  - **PV-10** The table follows Show. The header row and Player column stay pinned, and a Columns menu hides groups.
  - **PV-11** A heat tint shows whether each value is above or below the ranking value. The tooltip names the direction.
  - **PV-12** Clicking a row opens the player detail: all sources, by method.
  - **PV-13** Δ Prior week shows each value's change since last week. For DDF Value, both weeks use the same inputs.
  - **PV-14** Expand the chart to full screen *(JEG-483)*.
  - **PV-15** Expand the table to full height, with Pos / Team / Tier sortable *(JEG-483)*.
  - **PV-16** A Reset zoom link appears while zoomed and clears both brushes *(JEG-483)*.
  - **PV-17** Active filter chips, each clearing one filter *(JEG-483)*.

## Trade targets (TT)

  - **TT-01** The headline explains the page: "Where the trade market is wrong this week".
  - **TT-02** The Sell and Buy lists are both visible: top 5 each, expandable, side by side from 1280 px.
  - **TT-03** "Our value" defaults to DDF Value, with a source count on each row.
  - **TT-04** Each row shows the largest gap and which chart it's against. The row expands to show every chart.
  - **TT-05** Chart values are labelled "rescaled", with an ⓘ that explains the rescaling (GL-21).
  - **TT-06** A chart that is a week behind shows a "Wk N" badge wherever it appears.
  - **TT-07** A chart value at or below 0 is never a buy or sell target.
  - **TT-08** Players with only one source are included and flagged "◐ 1 source".
  - **TT-09** Market average *(to build: JEG-504)*:

      - Beside Our value, show the average of the compared rescaled charts (the ones picked in "Compare against"), and the difference between Our value and that average.
      - When the two are equal, show one column with a note that they're equal, rather than a duplicate column.

## Risers & fallers (RF)

  - **RF-01** Defaults to DDF Value, with series grouped in the picker. Counts the players it could not compare.

## Compare a trade (CT)

  - **CT-01** Give and Receive pickers, Swap, Clear, and a shareable link that carries the league settings.

  - **CT-02** The headline answers two questions in plain words, each with a confidence level (High / Medium / Low) *(to build: JEG-505)*:

1.  Should you propose or accept this trade? This is judged by DDF Value.
2.  Will a competing manager accept it? This is judged by the rescaled trade charts.

Confidence comes from how many sources agree. It drops to Low when any DDF Value in the trade is from one source, or when the DDF margin is under 5% of the total value traded. (Jeremy, 2026-10-09.)

  - **CT-03** The verdict is by DDF Value:

  - when charts disagree, it names them as the selling point;
  - when DDF Value is hidden, it follows the picked series and names it.

  - **CT-04** A waterfall for each source, all on one shared scale: give steps go down, receive steps go up, then the net.

  - **CT-05** An example trade shows before any player is added. It never goes into the link.

  - **CT-06** On phones, the verdict bar stays on screen.

  - **CT-07** Tiers are cut across all positions.

## How values work (HV)

  - **HV-01** Explains each view and lists the engine's series by method. It shows no numbers except the league card.

## Decision log

  - **2026-10-09:**

      - The Google Doc is the source of truth for contracts.
      - DDF is the core value.
      - League options rank above weights.
      - Front-end-only values may be computed in v2, tested independently.
      - Confidence = agreement + data quality; Low below a 5% margin.
      - The market average is over the compared charts.
      - Collapse works on every card and is remembered.
      - The low-confidence marker is "◐ 1 source".
      - DDF Value is one number per player in three versions, built from adjusted values only.
      - "As published" becomes "Trade charts (rescaled)".
