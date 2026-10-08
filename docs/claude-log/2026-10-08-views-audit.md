# 2026-10-08 views-audit (lane 12, branch fix/views-invariants)

Task: check whether Indexed, VORP vs waivers and Adjusted values hold
Jeremy's 2026-10-08 invariants for every source, fix the engine where needed,
gate the invariants, and expose diagnostics.

Mid-lane rule change (integrator, relaying Jeremy): no one-off math decisions
before the coordinated review. So this branch changes no plotted value. A full
implementation (option A) was built and verified, then moved to
`review/views-option-a` for the review. The options and numbers are in
docs/math-review-agenda.md under "From views-audit".

## Changed (this branch)

- `value-model.js`: read-only measurement helpers (`sharedTotals`,
  `groupShares`, `sharedGroupTotals`). `derivePublishedViews` additionally
  returns each chart's own `roles`. No output value changes.
- `curve-widget.js`:
  - `TradeValueCurveDiagnostics.viewInvariants`, informational, all three views
    measured on every rebuild.
  - `fixedPieDiagnostics` rows for published charts now carry the measured
    shared total, target and delta, labelled "not gated (published)". They were
    `{basis:"pipeline"}` with no numbers, on the stale premise that the pipeline
    indexes them. Still `ok:true`.
- `tests/test_view_invariants.py` (added to `test-core`): gates what already
  holds and prints the published measurements.
- `docs/methodology.md` (what holds today), `docs/math-review-agenda.md`
  (section "From views-audit"), `docs/risk-register.md` (updated GAP-VIEW-INVARIANTS-MEASURED and GAP-FIXEDPIE-SKIPS-PUBLISHED; added GAP-CBSROS-DIRECTION-RED and GAP-BENCH-LOW-ANCHOR).

## Verified (check named)

- `make sync` and `CHROMIUM_PATH=Chrome make validate`: exit 0 (final run,
  see commit).
- `tests/test_view_invariants.py` at the 12 combos, a custom roster (RB3 FLEX2
  BENCH8), and bench shares of 30% and 5%, in all three tabs:
  - CBS ROS, Razzball, the `*_adjusted` series and the raw series total the
    anchor's total to 1e-6 (180 gated checks).
  - Two broken engines are caught. Each is off by 0.05%, inside the page's own
    fixedPie tolerance: CBS ROS / Razzball total, and raw series total.
- Published-chart measurements (agenda VA-1) match the math inspector at Full
  PPR 12: USA Today +5.2%, FantasyCalc -23.0%, FantasyPros +22.4%,
  CBS -11.9%. Recomputed independently in Python from the plotted maps.
- Why fixedPieIndexed is green: the published charts were exempted (code
  read), and the saved values are `translate_ranked` output with no total step.
- Option A (branch `review/views-option-a`):
  - `make validate` exit 0.
  - Every invariant exact at the 15 settings.
  - 4 broken engines caught.
  - 12-combo sweep vs main: only the 4 published charts move. The numbers are
    in the agenda.
- CBS ROS direction / markup FAIL: shares measured at all 12 shapes with
  `tests/jeg68_markup_harness.cjs` (agenda VA-7). Code read: the split they
  judge is not displayed for CBS ROS or Razzball.
- Bench share 1-3% at Full PPR 12 blanks the chart on origin/main a1ff559
  (anchor pie off by 2.05). Reproduced on fresh pages and reported to the
  integrator. Risk row GAP-BENCH-LOW-ANCHOR.

## Claimed, not confirmed

- Option B (natives x one factor) peaks in the agenda are a Python
  computation on the plotted anchor. They were not run in the page.
- VA-6 option (b) (re-weight CBS ROS / Razzball in the Adjusted tab) was not
  measured.
