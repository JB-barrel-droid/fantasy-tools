<!--
Mirror of the Google Doc (source of truth): https://docs.google.com/document/d/1mI2vo4R74Fp-x14yR7ggh0T3WdcD6xjciLv7gVh4iJo. Regenerate when the Doc changes; never edit this file to change the contract.
Regenerate: python scripts/sync_feature_contract.py --doc contract <exported text>. Mirrored 2026-10-10.
tests/test_v2_contract_render.py reads every **XX-NN** ID below.
-->

# Data Driven Football: feature contract

**This doc is the source of truth for what the site must keep doing** (Jeremy, 2026-10-09).

A change that breaks a line does not ship. To change or remove a line, ask Jeremy first, then record his decision and the date under that line.

Each line has an ID. One contract test (tests/test_v2_contract_render.py, JEG-506) quick-checks every ID: the feature is present and its basic behaviour works. The repo keeps a mirror of this Doc (docs/feature-contract.md) and fails if any ID lacks a check. Deeper correctness tests live elsewhere. A line marked *(to build: JEG-xxx)* is agreed but not live yet; the test checks it once it ships.

Status: v1.2 (2026-10-10). Earlier versions are superseded.

## Everywhere (GL)

  - **GL-01** The brand is "Data Driven Football". "Vegas" never appears. "VORP" never appears; the term is "Value above waivers" (copy-vorp-002, 2026-10-22).

  - **GL-02** Every number is right at its source:

  - Engine values equal the engine.
  - Values that exist only on the front end are computed in v2 from engine values, then tested against an independent calculation.
  - Each front-end value gets its own named contract line once it ships: the CT-02 confidence and the TT-09 market average, then trade nets and gaps. (Jeremy, 2026-10-10.)
  - (Jeremy, 2026-10-09: "There are some values that are only calculated on the front end, in which case math must be done there.")

  - **GL-03** Missing values:

  - A player missing from a fully loaded chart is worth 0, shown as "0.0".
  - "—" appears only when the engine returns null, always with its reason.
  - A DDF Value from a single source is shown with a "◐ 1 source" tag, and the tooltip explains it.

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

  - **GL-08** DDF is the core value everywhere. ESPN is one input, not the anchor. Defaults, tiers and wording use DDF Value, including Trade targets' "Our value" (Jeremy, 2026-10-16: DDF decides who we want and don't want).

  - (Jeremy, 2026-10-09: "ESPN is no longer the core weight, it is DDF".)
  - Moving the rescaling anchor to DDF is JEG-499.
  - The source-neutral pipeline (JEG-508) updates this section.

  - **GL-09** Three DDF Value versions are available on every page: the blended DDF Value, DDF Value from trade charts only, and DDF Value from player projections only. Blended is shown by default; the other two are off by default *(to build: JEG-497)*. Each version is one number per player, the same on every tab and view, and is the equal-weight mean of adjusted values only. (Jeremy, 2026-10-09.)

  - **GL-10** The reader's selection (series, DDF inputs, ranking) is remembered on this device.

  - **GL-11** Changes to league settings apply as they change: no Apply or Save step. Rapid changes are one recompute; an invalid in-between state keeps the last valid results and says why; Find a trade re-reads the pasted roster text and re-runs under the new settings. *(Changed 2026-10-24 from "a draft until Apply", Jeremy, JEG-1020.)*

  - **GL-12** The bench share shown is the one the engine computed from the reader's settings (the readout in GL-23) or, when the override is on, the reader's own number. v2 does no math on it.

  - **GL-13** On phones (390 px), no page scrolls sideways and every tab is usable.

  - **GL-14** If the engine fails, the page shows a failure state, never stale or partial numbers.

  - **GL-15** Rescaled trade charts keep each publisher's own ranking order. A guard checks this on every build (JEG-482).

  - **GL-16** Tier (Starter / Bench / Waiver) follows the ranking series in use, which is DDF Value by default.

  - **GL-17** Every module can be expanded beyond its default size *(Player values: JEG-483; the other pages: JEG-500, done)*.

  - **GL-18** Every module can be collapsed with a chevron *(JEG-500, done)*:

  - Collapsed, it shows its title and a one-line summary, so nothing gets lost.
  - The state is remembered on this device.

  - **GL-19** On desktop, ⓘ buttons open on hover as well as on click. They stay keyboard- and touch-accessible *(to build: JEG-501)*.

  - **GL-20** Search finds every player in the active NFL universe, including unrostered and practice-squad players. A player with no value appears only in search results, shown as "0.0" with the reason *(to build: JEG-502)*.

  - (Jeremy: "The user knowing they are a 0 is better than the user questioning why they aren't in the tool.")

  - **GL-21** Publishers' trade charts, put on our point scale, are called **"Trade charts (rescaled)"**. Never use "as published" or a bare "indexed" as a label. One-line meaning: "Each publisher's trade values, rescaled to our point scale for your league; their ranking order is unchanged." *(to build: JEG-510)*

  - **GL-22** League options rank above weights. "Edit league" is the primary control. "Position weights" (renamed from "Weights & bench") is secondary when they are shown together *(to build: JEG-498; the rename shipped with JEG-537)*. (Jeremy, 2026-10-09 / 2026-10-10.)

  - **GL-23** The bench share is a readout, not a slider: "Bench share this week: QB x%, RB y%, WR z%, TE w%, from your league settings". It comes from the engine. A bench-share override is off by default; when it's on, it shows the old 1–30% slider (Advanced in Your league), with a reset link in Position weights. *(JEG-537; pinned by `tests/test_v2_advanced_render.py`)* (Jeremy, es-value-001, 2026-10-09.)

  - **GL-24** Edit league includes:

  - last regular-season week (default 14);
  - playoff weeks (default 15–17);
  - "Optimize for": Whole season (default) / Regular season / Playoffs;
  - a collapsed "Advanced" section at the bottom: injury history (Recent seasons default / All seasons equally); projection confidence (Less / As measured default / More); the bench-share override.

Share links carry every setting. League weeks use `regend`, `playoffs`, `optimize` and `week`; the advanced settings use `inj`, `conf` and `bso` (three decimals, absent = off), each written only when it differs from the default. Old links: `bench=0.150` means no override and any other `bench=` without `bso=` is the sender's override. *(JEG-537, JEG-527; pinned by `tests/test_v2_advanced_render.py` and `tests/test_v2_share_render.py`)* (Jeremy, 2026-10-10.)

  - **GL-27** Every source name is a link to that publisher's page for the served week, opening in a new tab (the addresses ship in `assets/comparison-sources-data.json`; ESPN has none and stays plain text). A projection source with a page per position uses the player's position in row context and the QB page in header context. A link in a column header never sorts the column, and a link in Customize never toggles the source. Places: Trade targets column heads, chart values and the "Compare against" choice, the Showing legend, Player values column heads, Customize, Compare rows and the player drawer. *(JEG-457; pinned by `tests/test_v2_source_links_render.py`)*

  - **GL-26** Our names are defined once and shown wherever they appear, with an info button: DDF Value is our estimate of what a player is worth, blended from the sources you have chosen (JEG-822); DDF Projections is what production supports; Trade chart average is what the market will pay. The edge: buy below DDF Value and sell above it, best when DDF Value says you win and the market says you lose. The buttons sit on the header row (which reads "On the chart:", not "Showing:"), Risers & fallers' Movement picker and disagreement card, the DDF Value group in Customize, and the Compare deal-read nets. *(JEG-490; pinned by `tests/test_v2_names_render.py`)*

  - **GL-25** A source that disagrees with the other sources more than usual shows a small "Check" chip next to its name, in the slot the prior-week badge uses, with the published message as its tooltip (`source_divergence` in `assets/reference-freshness.json`, JEG-460). A reviewed source shows "Reviewed", linking to its resolution issue where a link is allowed. The chip never hides a source or blocks anything. Our own DDF Value and VORP columns carry none. *(JEG-609; pinned by `tests/test_v2_divergence_chip_render.py`)*

  - **GL-28** The default league is 12 teams, PPR, 1 QB / 2 RB / 2 WR / 1 TE / 1 FLEX / 1 K / 1 DEF with 7 bench slots. Edit league has stepper rows for K and DEF (0 to 3; set both to 0 for a league without them); K and DEF are roster slots only and have no values. The bench is explained as how many players real leagues roster at each position (the market bench), never as a fixed mix. The Tier column is headed "Tier" and, for every ranking series, shows Starter / Bench / Waiver from that series' rank against the engine's convention zones (GL-16). *(JEG-565; pinned by `tests/test_v2_panels_render.py`)* (Jeremy, 2026-10-10.)

## Manifesto (MF)

  - **MF-01** The Manifesto is the first section of the Writing tab (`#writing/manifesto`; the old `#manifesto` redirects there) and carries Jeremy's text verbatim, checked word for word against a repo copy that is updated only from his Google Doc. It is plain text with no controls. The landing tab stays Trade targets *(JEG-494)*.
  - **RS-01** Manifesto, How values work and Research are sections of one Writing tab and appear in that order inside it (`#writing/manifesto`, `#writing/how-values`, `#writing/research`); they are not top-level tabs, and the old `#manifesto`, `#how-values`, `#research` and `#research/<slug>` routes redirect into the matching section. The Research section is an index of the published posts, each with title, one-line summary and date. A post routes at `#writing/research/<slug>`. A draft never reaches the build. Pinned by `tests/test_v2_research_render.py` *(JEG-543)*.
  - **RS-02** Every published post was approved by Jeremy as a Google Doc before its `published` flag was set. Reading layout matches the Manifesto (about a 70-character column, no league or Showing bar unless a post embeds a live widget that needs them). *(JEG-543; process rule, not machine-checked)*
  - **RS-03** Live widgets in a post read the engine, and a what-if never changes the reader's saved league settings until they press Apply. *(JEG-543; no widget ships with the framework, so nothing to check yet)*

## Player values (PV)

  - **PV-01** The default view is DDF Value against the rescaled trade charts.
  - **PV-02** A chart of trade value by rank. The DDF Value line is drawn on top and heavier than the others.
  - **PV-03** Zooming the chart shows player names on the points. (Jeremy, 2026-10-08: "I like the feature when you zoom in on the chart you see the names.")
  - **PV-04** The chart marks where Starter turns to Bench and Bench turns to Waiver *(JEG-503; pinned by `tests/test_v2_chart_zones_render.py`)*:

      - vertical lines at each break;
      - "Starter", "Bench" and "Waiver" across the top of the chart area, centred in their sections, in light grey;
      - across positions, each line sits where the break really falls.
  - **PV-05** An X rank brush and a Y value brush. Dragging either one updates Show and the table.
  - **PV-06** Grabbing the middle of a range brush moves both ends together, keeping the width; Shift+arrow on the fill does the same *(JEG-503; pinned by `tests/test_v2_chart_zones_render.py`)*.
  - **PV-07** Clicking a source name in the chart legend turns that series on or off, among the series picked in Customize; the entry shows on or off with a symbol, and the ranking series stays on *(JEG-503; pinned by `tests/test_v2_chart_zones_render.py`)*.
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

  - **PV-18** The chart's Y axis follows the top and bottom visible points (values of 0 ignored), with about 4% padding and nice steps, so the lines show more differentiation *(JEG-477; pinned by `tests/test_v2_chart_fit_render.py`)*.
  - **PV-19** A player that no shown series (DDF Value included) prices above 0 is hidden, with a note saying how many; a search finds him again, as a 0 *(JEG-477)*.
  - **PV-20** Rank by always offers the DDF weighted projections (ESPN, CBS rest of season, Razzball) as well as the three DDF Value versions, shown or not; ranking by one puts it on the chart and in the table *(JEG-477)*.

## Trade targets (TT)

  - **TT-01** The headline explains the page: "Where the trade market is wrong this week".
  - **TT-02** The Sell and Buy lists are both visible: top 5 each, expandable, side by side from 1280 px.
  - **TT-03** "Our value" defaults to DDF Value, the blend (Jeremy, 2026-10-16: DDF decides who we want and don't want; this reverses the JEG-677 DDF Projections default), with a source count on each row. DDF Projections, the other DDF versions and the projection series stay in the picker (JEG-542).
  - **TT-04** Check 1 ranks by the market consensus: the median of the INDEXED trade charts (the rescaled series, not the adjusted or native values) that price the player, minus our value (Jeremy, 2026-10-16). The consensus and each individual chart are used to find opportunities for both value and offer acceptance. A player is listed only with 2+ charts and a majority of them on the consensus's side of our value; Sell is gap > 0, Buy gap < 0. Each list ranks by the gap it shows weighted by the value at stake, score = |gap| x min(our value, consensus), biggest first; every row shows that score, so the order on the page follows the numbers on the page. Sell shows the consensus gap and also needs our value >= 5 (`SELL_FLOOR`): a player we would drop is a drop, not a trade chip, and is counted in a note instead (JEG-820, option B, 2026-10-22, proceeding per standing instruction; Jeremy to confirm). Buy shows the gap at the charts' rank (JEG-833, 2026-10-22, proceeding per standing instruction): for a player the charts rank r-th at his position, our r-th value at that position minus our value (`rankGap`, computed over every compared player, a name search only filters the list); a Buy needs it at or under -2 (`BUY_RANK_MARGIN`), the phone card says where the charts rank him and where we do ("RB8→RB5": the charts rank him RB8, we rank him RB5; the table row carries it in the score's tooltip), and the players the charts price below our value but rank where we do are counted in a note as our steeper scale, not a mispricing. The market cell's ▲ / ▼ line says "3.3 above" or "3.3 below", never a signed number against the gap. Each row shows the consensus, the gap, "N of M charts agree" and one dot per chart, each dot carrying that chart's indexed value. This replaces the old "largest gap, from one chart" attribution. The row expands to show every chart. *(JEG-677; pinned by `tests/test_v2_targets.py` and `tests/test_v2_targets_render.py`)*
  - **TT-05** Chart values are labelled "rescaled", with an ⓘ that explains the rescaling (GL-21) *(to build: JEG-510)*.
  - **TT-06** A chart that is a week behind shows a "Wk N" badge wherever it appears: Trade targets, Player values and Compare a trade.
  - **TT-07** A chart value at or below 0 is never a buy or sell target.
  - **TT-08** A player whose DDF Value rests on fewer than 2 sources gets no Sell or Buy call; the notes say how many were left off and why ("only 1 source"). (Jeremy, 2026-10-27, JEG-1186: "Suppress"; replaces the 2026-10-09 line "included and flagged ◐ 1 source".) A player priced by only one trade chart is not a Check 1 target either (TT-04: 2+ charts).
  - **TT-12** Hovering, focusing or tapping a chart value on Trade targets shows where it comes from, leading with the number as the publisher prints it: as published, times the index factor, equals the indexed value, minus our value, equals the gap, with a link to the chart. The numbers come from the engine's derivation (`getPublishedMath`); a player the chart does not price shows the reason instead. *(JEG-457; pinned by `tests/test_v2_source_links_render.py`)*
  - **TT-10** The page runs two numbered checks, and the subtitle names both: "1. Potential mispricing" (player by player) and "2. Potential positional weight inflation" (position by position). *(JEG-476)*
  - **TT-11** Check 2 compares DDF Value with the trade-chart consensus (median of 2+ charts) and with each chart, by position and by DDF starter / bench tier. The gap is the group's share of the market total divided by its share of the DDF Value total, minus 1, over the same players on both sides, so a chart's overall scale cannot make every position look cheap. Sell this group at +10% or more, Buy this group at -10% or less, else Fairly priced. A group under 3 players shows no number; the headline only names groups of 8 or more. A group opens to its players. *(JEG-476, JEG-489; pinned by `tests/test_v2_group_weight.py` and `tests/test_v2_group_weight_render.py`)*
  - **TT-09** Market average *(to build: JEG-504)*:

      - Beside Our value, show the average of the compared rescaled charts and the difference between Our value and that average.
      - When the two are equal, show one column with a note that they're equal.

## Risers & fallers (RF)

  - **RF-01** Defaults to DDF Value, with series grouped in the picker. Counts the players it could not compare.

  - **RF-02** "Where DDF Value and the projections disagree" (JEG-1073 names): compares the change in DDF Value (the Adjusted trade chart average) with the change in DDF Value (projections), week over week and like for like (a source without a saved prior week is left out of both weeks). Two lists: "DDF Value moved, projections didn't" and "Projections moved, DDF Value didn't". A player qualifies when one side moved 2.5 points or more either way and the other 1.0 or less. Each player gets a rule-based read: market up only, "Buying in without the production: sell"; market down only, "Panic the projections don't share: buy"; projections up only, "Market hasn't caught up: buy"; projections down only, "Market hasn't reacted: sell". With no prior week for either series it says so and lists nothing. *(JEG-488; pinned by `tests/test_v2_disagree.py` and `tests/test_v2_disagree_render.py`)*

## Compare a trade (CT)

  - **CT-01** Give and Receive pickers, Swap, Clear, and a shareable link that carries the league settings.

  - **CT-02** The verdict card carries no "Should you propose or accept?" or "Will they accept?" lines, and no "Our value: ..." or "Charts agree: ..." level. The Deal read (CT-08) carries the answer. *(Jeremy, 2026-10-26, JEG-1112 option D, "drop the two 'propose / accept' heads": they repeated the Deal read and pushed the give / receive / verdict block past the fold at 1366x768 and 1440x900. Retires the JEG-505 / JEG-895 headline answers; pinned by `tests/test_v2_contract_render.py` and `tests/test_v2_compare_empty_side_render.py`)*

  - **CT-03** The verdict is by DDF Value:

  - When charts disagree, it names them as the selling point.
  - When DDF Value is hidden, it follows the picked series and names it.

  - **CT-04** Each source gets a waterfall, all on one shared scale: give steps go down, receive steps go up, then the net.

  - **CT-05** An example trade shows before any player is added. It never goes into the link.

  - **CT-06** On phones, the verdict bar stays on screen.

  - **CT-07** Tiers are cut across all positions.

  - **CT-08** A rule-based deal read replaces "The sources split." It is driven by logic, never a language model. Three nets, each with an ⓘ definition: DDF Value (are you getting real value?), Trade chart average (does the market think you are winning?), DDF Projections (is the value backed by projected production?). The side of a net is Win at or above max(1, 3% of that series' average side total), Lose at or below the negative of that, otherwise Even. The read is a fixed 9-cell table on (DDF Value, Trade chart average): Win with Lose is "Arbitrage: send it" (the other manager sees it as their win); Lose with Win is "Trap"; the rest are listed in `app/v2/trade.js`. One production sentence compares DDF Projections' side with DDF Value's. The page shows the 3x3 grid (DDF Value rows, Trade chart average columns) with the current cell outlined. A trade with no Trade chart average or DDF Value for a player has no read, with the reason. *(JEG-487; pinned by `tests/test_v2_deal_read.py` and `tests/test_v2_deal_read_render.py`. Stacked give/get bars from the prototype are not built: the verdict waterfall already shows the steps.)*

## How values work (HV)

  - **HV-01** Explains each view and lists the engine's series by method. It shows no numbers except the league card.

  - **HV-02** How values work leads with the three numbers (DDF Value, DDF Projections, Trade chart average) and "Where the edge comes from", with no numbers in that copy; "Data Driven Adjustments" and "DDA" are retired from it. *(JEG-490)*

## Decision log

  - **2026-10-09:**

      - The Google Doc is the source of truth.
      - DDF is the core value.
      - League options rank above weights.
      - Front-end-only values are allowed, and are tested independently.
      - Confidence = agreement + data quality; Low below a 5% margin.
      - The market average is over the compared charts.
      - Collapse works on every card and is remembered.
      - The low-confidence marker is "◐ 1 source".
      - DDF Value is three versions built from adjusted values only.
      - "As published" becomes "Trade charts (rescaled)".
      - Bench share becomes a readout (es-value-001).
  - **2026-10-10:**

      - GL-11 split: draft-until-Apply stays GL-11, and the primary-control part becomes GL-22.
      - "Weights & bench" is renamed "Position weights".
      - TT-05 is marked to build in JEG-510.
      - GL-02's front-end values get named lines as they ship.
      - MF-01 is checked word for word against a repo copy.
      - TT-06 is checked on Trade targets, Player values and Compare.
      - The contract test may fake one-source players so the ◐ check can always fail.
      - New lines: GL-23 (bench-share readout) and GL-24 (Edit league weeks, Optimize for, Advanced). "Optimize for" defaults to Whole season, and league options and Advanced sit in Edit league.
      - Unvalued players appear only in search results.
      - Blended DDF Value is shown by default; the charts-only and projections-only versions are off.
