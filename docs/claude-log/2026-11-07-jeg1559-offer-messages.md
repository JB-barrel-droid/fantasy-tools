## 2026-11-07 - JEG-1559 Build a Trade offer messages by offer shape (+ pasted-league fix, #trade-charts anchor)

Contract (Jeremy, 2026-11-07): "the section with copy to grab to make an offer is not thoughtful enough and is too
simplistic. Reduce redundant options, and show or hide options based on the shape of the offer." Additions the same
day: a #trade-charts anchor for "N/4 public trade charts" links; the partner's roster % (JEG-1558) in the pitch, with
a clear loss switching to a counter-ready ask; a slot for the natural-fit rationale (JEG-1561); and the bug where the
"Add your league to see..." card showed with a pasted league loaded.

Audit of the old options (9 buttons, all shown for every offer):
- Friendly, Straightforward, Direct offer: the same terms + optional chart claim with different filler. Redundant.
- Brief: the terms alone. Same job as a short opener.
- Analytical: terms + chart claim, else the Analyst charts average, else "How does this fit your roster?"; its lineup
  sentence used fixed sample numbers. Same job as the value option.
- 2-for-1 consolidation: shown for 1-for-1 too ("a swap"). Swap positions of need: shown for same-position trades and
  with no roster data ("deep where the other is thin" was a guess). Ask what they want: shown for every offer.
- Shop a player: the only one that fits an empty receive side (others were disabled then).

New (app/next/build-offer.js, pure; build-trade.js builds its input and renders):
- Shape: size (1-for-1, equal counts, you consolidate, you add depth, shop), add-ins (Analyst charts under 1.0),
  same/cross position, value balance by Analyst charts and by DDF Value (near even within 10% of the larger side,
  the verdict's band), fills their need (tradeFit `them.towardAt` at a position you send, league only), their bench
  player for a lineup upgrade (league only), the JEG-1558 roster % labels. A one-line summary sits above the options.
- Options (at most 5, one preselected): Short opener (always); Offer with the numbers (only when the picked chart, or
  the best chart when none is picked, supports the pitch; picking it syncs the chart picker); Consolidation pitch
  (you send more players); Depth pitch (you ask for more); Fills their need (league data says so); Counter-ready ask
  (Analyst charts favor you, or JEG-1558 band clearly_worse); Shop a player (nothing asked for, alone).
  Preselect: ask > value > need > opener; a reader's own pick is kept while it stays available.
- Roster % (JEG-1558 band, from DDFOpportunity.rosterImprovementPct when the module is on the page): better "It makes
  your roster about X% better."; unchanged "It barely changes your roster (about X%)."; slightly_worse "It costs your
  roster only about X%, so it's close."; clearly_worse: no roster line, counter-ready ask preselected; unsized/absent:
  nothing. Never a promise of acceptance.
- JEG-1561 slot: `rationale: {text}` appended to the value option; null today (module not published yet).
- Draft picks: the engine has no pick values and the page cannot add a pick, so there is no picks shape.

Other changes
- League read: build.html loads `v2/team-summary.js` + `ddf-league.js` and reads `DDF.league.current()` (link, pasted,
  saved) after `DDF.league.ready`; a loaded league opens My league; the Any-players "Add your league to see..." card
  shows only without a roster (`any-noleague`). Root cause of Jeremy's screenshot: the page read only DDF.link and
  `ddf.v2.workspaces`, not `ddf:pasted`.
- `#trade-charts` (was `#charts-section`): a link with it scrolls to the charts after the trade renders, below the
  sticky header and sub-nav; no anchor, no scroll.

Independent review (separate Opus subagent, head 79cf42eb6): CHANGES NEEDED, fixed in the next commit:
- An explicit None in the chart picker was overridden (the value option re-picked the best chart), and the auto-picked
  chart stuck after a trade change and leaked into other pitches. Now the reader's pick (`S.chartUser`: a chart key or
  'none') is kept apart from the auto chart, which is re-picked on every render only while the value option is on;
  None removes the value option; other pitches cite only the reader's pick.
- The counter-ready ask's hint says "A clear loss for their roster" when it shows for the roster band, not the charts.
- A shared link league without settings maps to 'pasted'; the #trade-charts scroll runs once.
- Tests: picker None and auto chart, the reader's option and edits surviving an engine rebuild, pasted league in Any
  players mode.

### Verified (check named)
- `node tests/node/build_offer_check.cjs`: 18 shape rows (sizes, add-in, positions, balance both ways, need, bench,
  league-only gating, shop, unknown analyst value, the five JEG-1558 bands): ids, preselect, exact texts, and for every
  option "Hi!", no site name, no choose/set up, no acceptance promise, at most 5 options.
- `tests.test_build_offer_render`: at 1440 and 390, buttons = DDFOffer.options(page input), one pressed = preselect,
  message = its text, clicking another replaces it, Copy message reports copied, no overflow; #trade-charts lands
  below the header and no anchor means no scroll; a ddf:pasted-only league hides the card and shows the trade checks,
  no league shows the card.
- Regression: `tests.test_build_page_engine_parity`, `tests.test_build_swap_routes`, `tests.test_build_root_pages`,
  `tests.test_launch_copy_guard`, `tests.test_page_load_no_404`; `node tests/rendered_gate/gate.mjs dist`.
- QA sweep (scratch `qa_build.py`, 16 views at 1440/390): 0 console/page errors, 0 failed requests, 0 overflow,
  0 banned words, no "DDF" or team names in messages.

### Claimed, not confirmed
- CI shards on the PR head (see checks); live verification on JEG-1559 after deploy.
- The JEG-1558 roster line is tested with stubbed module output only; it appears live once ddf-opportunity.js is
  loaded on build.html (one script tag, after JEG-1558 merges).
