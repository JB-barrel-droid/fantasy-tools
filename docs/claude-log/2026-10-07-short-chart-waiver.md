## 2026-10-07 - Short published charts: waiver line from the other charts (V2-WAIVER-COVERAGE)

Contract: implement Jeremy's 2026-10-07 decision on short charts. His words:
"If needed for computations, cover them by extrapolating from the average of
other charts. Denote them. Where it's not needed, hide those values." Keep the
server and the browser in exact parity. Run the 12-combo sweep. Branch
`fix/short-chart-waiver`, not merged.

### What changed
- **Method** (`unified.impute_extension` / `ValueModel.imputeExtension`). This
  applies only at a position where a chart lists no more players than the
  league rosters.
  - The chart is extended with imputed natives for players it does not list.
  - Peers are the other published charts' saved 12-team natives at the same
    scoring.
  - For each peer, k = sum(chart) / sum(peer), taken over the players both list
    in the bottom half of the chart's list (value <= its median listed value).
    A peer is used only if at least 3 players qualify.
  - Each omitted player's imputed native is the mean of k x peer native over
    the usable peers that list him. It is capped at the chart's last listed
    value.
  - The extension is ordered by that value, then by player key.
  - The roster allocation and the waiver line use the extended list.
    `waiver_method` is `imputed_from_other_charts` and `n_imputed` records how
    far past the list the line reads.
  - If no peer is usable, the old fallback stays (`insufficient_coverage`).
  - Imputed players never get a value: `translated` holds listed players only.
- **Deviations from the brief, and why.**
  - The mapping is proportional and fitted on the tail. It is monotone and has
    one number per peer, and the tail is where the line is extrapolated.
    Several charts have floors (CBS 5.0, FantasyPros 1.0), so a whole-list fit
    would follow the top of the chart instead.
  - The cap at the chart's last listed value is my addition. A chart that
    omits a player values him at most at its last listed value. Without the cap
    the extension could rank above listed players.
  - Because of the cap, FantasyPros (RB/TE at 12 teams; RB/WR/TE at 14) and
    FantasyCalc (RB/WR at 14) are extrapolated, but their line lands on their
    own floor. Their values do not move. They are still denoted.
- **Server.** `translate_ranked(peers=)`, `translate_natives(peers=)`,
  `peer_natives`, `waiver_summary`; `translate_source` loads peers from the
  fixture (Supabase record, lineage card).
  - `translate_via_vorp.py` passes peers: the document in fixture mode, the
    current fixture in section mode.
  - It records `translation.waiver` and `translation.waiver_imputation`
    (version, peers, imputed and short positions) on every saved combo.
- **Chain.** `run_retranslate` re-translates the whole promoted fixture
  (`--fixture --translation natives`) after the per-source stages and before
  the fit. A chart's saved values now depend on the other charts' natives. A
  failure here fails the fit stage.
- **Browser.** `translatePublishedVorp({peers})`, `derivePublishedSetup({peers})`
  (result `waiver`), `derivePublishedViews({natives})` (per-source `waiver`),
  and `publishedWaiverInfo`.
  - `curve-widget.js` and `comparison-dashboard.js` pass the other three
    charts' saved natives.
  - Denotation:
    - `getSourceInfo()[].waiverNote` / `.waiver`
    - `TradeValueCurveDiagnostics.publishedDerivation[src].waiver` (saved and
      derived modes)
    - the chart caption: "waiver line extrapolated from other charts: CBS (QB,
      RB, WR, TE)"
    - the v2 Sources and Freshness lists append the note to the chart's line.
  - Versions: `unified-py-jeg62/2`, `league-settings-001/4`,
    `published-views-001/2`, `other-charts-tail-ratio/1`.
- **Fixture.** Re-translated in fixture mode with week 5. Only CBS values and
  every published combo's new provenance keys changed (checked with a JSON
  diff).
  - `cbs_adjusted` was rebuilt from the new raw values on the COMMITTED fit
    cells.
  - The cells were not refit locally. A local fit differs from the CI fit for
    every source (`ddf_leg_sha256` and `pie_source` differ), so it would be
    unrelated churn.
- **Docs and recorded numbers.** `docs/methodology.md` has a new "Short charts"
  section. Risk rows V2-WAIVER-COVERAGE (fixed in branch) and CTL-006
  (no-imputation applies to displayed values) are updated.
  - `tools/guard_harness.mjs` EXPECTED_JEG5 was re-recorded: the simulated
    broken state now misses the pie by +59.5 (19/114 tier mismatches), still
    far outside the tolerance of 2. The CBS adjusted values changed under
    Jeremy's rule. The target had also moved on main (2329.32), and main's
    recorded numbers were already stale there: the test fails on origin/main
    0548ed2.
- **Tests changed** (rule changed by Jeremy):
  - Version pins were bumped in three tests.
  - `test_published_views_engine` "nobody is 0" now exempts a chart whose
    waiver line is extrapolated past its list at every position. CBS can now
    have nobody at 0.
  - A mutation anchor was updated (code text only).
  - The reference implementations in the engine tests now pass the same peers
    as the browser.

### Verified (check named)
- `tests/test_short_chart_waiver.py` (new, 11 tests, wired into test-unit). It
  covers:
  - the imputation arithmetic by hand;
  - the cap;
  - a short position pricing its last listed player (without peers it was 0);
  - imputed players never valued;
  - no peer coverage keeping `insufficient_coverage` with the last listed
    value;
  - charts that are never short (USA Today, FantasyCalc at 12 teams) being
    byte-identical with and without peers;
  - CBS imputed at every position at 12 teams;
  - Python == JS `imputeExtension` on 14 vectors (955 imputed rows, exact);
  - five JS mutations each caught (8-36 failing vectors): cap dropped,
    whole-list fit, sum not mean, peers ignored, line at the list end;
  - the saved fixture equal to the peer-extended translation, and the old
    end-of-list CBS values caught (6 problems).
- The new test was run against origin/main code: 11/11 fail (errors).
- `tests/test_vorp_translation_js_parity.py`: every real vector now carries
  peers. Result: 1301 vectors, 776,552 numbers, max diff 0. Two synthetic
  vectors were added (thin with peers, thin without coverage). The stored-drift
  check now also requires `translation.waiver` to equal the recomputation. All
  existing negative tests still fail as intended.
- `tests.test_rebuild_chain_failclosed`: two new tests. The fixture is
  re-translated once, after the last promotion and before the fit. A
  re-translate failure fails the chain.
- `tests.test_published_league_settings_engine` and
  `tests.test_published_views_engine` pass, including all their mutation
  tests.
- `tests.test_guard_harness_recorded` passes after the re-record.
- 12-combo sweep (3 scorings x 8/10/12/14 teams) on `make sync` builds, run in
  system Chrome. Baseline: origin/main 0548ed2. Branch: this branch, rebased
  onto it, with the fixture re-translated from main's fixture (byte-identical
  to git's automatic merge of the fixture). The same sweep against 3ddf90d
  gave the same picture. All four
  published charts and `cbs_adjusted` were toggled on.
  - `fixedPieIndexed` true on both sides for all 12 combos.
  - `sourceScaleAgreement` is the same on both sides in every combo: true at
    full PPR / 12 teams; false in the other 11 combos, with identical
    offenders on both sides (WR/TE OUR_MAX vs the anchor; this predates the
    branch).
  - Values that move: CBS and `cbs_adjusted` only. ESPN, USA Today,
    FantasyCalc, FantasyPros, their adjusted series and every other series are
    unchanged in every combo.
  - Position starts (top value per position) are unchanged for CBS raw (its top
    player is the positional max by construction). `cbs_adjusted` starts move
    by <= 0.02, and its peak by <= 0.02.
  - Full PPR CBS, players CBS lists but that were at 0 and are now priced:
    | Teams | Newly priced | Notes |
    | --- | --- | --- |
    | 12 | 13 | Matthew Stafford 0 -> 5.6; Ollie Gordon II, Rachaad White, Alvin Kamara 0 -> 3.7; Rome Odunze, Jordyn Tyson 0 -> 3.8 |
    | 10 | 13 | Stafford 0 -> 4.7 |
    | 14 | 13 | Stafford 0 -> 6.1 |
    | 8 | 1 | Stafford 0 -> 1.7; RB/TE lines still fall inside CBS's list |
  - CBS players who were already priced only rise (median +2.7 at 12 teams, max
    +5.3; median +3.5 at 14 teams). The lower waiver line shrinks the gap to the top player. Standard
    scoring at 12 teams prices 22 more.
  - Full PPR 12-team waiver lines (CBS units): QB 6.0 -> 1.06, RB 5.0 -> 2.3,
    WR 5.0 -> 1.5, TE 5.0 -> 2.04. The implied flex moves RB 9 -> 5, WR 3 -> 6,
    TE 0 -> 1, because the flex weights are measured against the extended
    lines.
  - The caption shows "waiver line extrapolated from other charts:
    FantasyPros (RB, TE), CBS (QB, RB, WR, TE)" at full PPR 12 teams, and
    "CBS (QB, WR)" at 8 teams. No page errors.
- v2 (`dist/v2/`, Chrome at 1440 and 390): the Sources popover shows the note
  on the CBS and FantasyPros lines. No horizontal overflow and no page errors.
  A screenshot was checked at 390.
- `CHROMIUM_PATH=<system Chrome> make validate` exit 0, on 0548ed2 and again
  after the final rebase onto 9b97f88 (no fixture change on main). On 9b97f88,
  64 tests also pass: the new and parity tests, the engine and render tests,
  `test_v2_how_render`, `test_v2_targets_render` and
  `test_below_leg_zero_render`. The v2 note check was repeated there too.
- One combined run of 11 test modules showed 4 transient ERRORs in the two
  published render tests. They did not reproduce in three reruns (alone,
  render-only, and the same combined list): OK.
- Every `make test-unit` module was run one at a time on the final rebase. All
  pass except four, and each of the four also fails on origin/main 0548ed2:
  `tests.test_trade_chart_ingest_ci`, `tests.test_adjustment_inputs` (a missing
  versioned inputs file), `tests.test_jeg68_starter_markup` and
  `tests.test_jeg69_direction_check` (both on CBS rest-of-season markup).
  `tests.test_lineage_vorp_roundtrip` (espn leg, not in test-unit) also fails on
  main. `tests.test_guard_harness_recorded` was red on main and is green on the
  branch after the re-record.
- The regenerated `dist/` and app copies were reverted before the commit.

### Claimed, not confirmed
- The next comparison-chain run refits the CBS adjustment cells against the new
  CBS raw values. Until then `cbs_adjusted` uses the old cells on new raw
  values. Not run: the fit needs the CI environment's DDF leg to reproduce.
- The Supabase `publisher_translated_values` / `publisher_roster_assumptions`
  record picks up the new values and `waiver_method` on the next
  `refresh_vorp_translation` run. No Supabase writes were made here.
- The VORP-vs-waivers and Adjusted views were checked by the engine tests, not
  in the browser sweep. The saved full-PPR `vorp_views` come from
  `build_imputed_vorps.py`, a method with no waiver line, and are unaffected.
- The tail-ratio mapping and the cap are my reading of "extrapolating from the
  average of other charts". Jeremy should review them.
