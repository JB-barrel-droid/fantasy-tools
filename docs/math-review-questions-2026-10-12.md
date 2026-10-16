# Math Review Questions for Jeremy (JEG-450)

Review conducted 2026-10-15 on `origin/main` eba4f38a (Week 5 data).
Every carried item from `docs/math-review-agenda.md` was verified against the
current code. Clear defects: none found. The VP spec (JEG-508) and expected
starts (es-value-001) resolved most of the original 27 items. Below are the
remaining judgment calls.

---

## Q1. GAP-TIER-FROM-ESPN: should the tier follow the selected "our value" source?

**Context.** The v2 tier label (Starter / Bench / Waiver) always comes from
ESPN's slot fill, even when the user picks CBS ROS or Razzball as "our value."
A player another source prices as a starter can show an ESPN Waiver tier.

**Options.**
- (A) Keep ESPN tiers everywhere (current). Simple; one consistent tier scheme.
- (B) Tier follows the selected "our value" source's slot fill (a CBS-ROS-selected
  chart would show CBS ROS tiers).
- (C) Label the tier column "ESPN Tier" so the source is explicit.

**Recommendation:** (C). It is the smallest change that removes the confusion,
and the tier still means the same thing across sessions.

---

## Q2. GAP-ADJ-IDENTITY-FALLBACK-UNLABELLED: label or pool the five identity cells?

**Context.** Five of the 56 old adjustment cells fell back to identity (no
adjustment) because too few fit pairs existed. The fit and `*_adjusted` series
were retired in PR 532, but the `*_adjusted` keys still exist as deprecated
aliases carrying each chart's Adjusted values. No fit cells are used.

**Options.**
- (A) Close as moot -- the fit is retired; the aliases carry Adjusted values
  which use no cells. The gap no longer applies.
- (B) Keep the gap open in case the fit returns in a future feature.

**Recommendation:** (A). The fit is removed. Close the gap.

---

## Q3. GAP-CBSROS-DIRECTION-RED: demote the CBS ROS direction and markup checks?

**Context.** The CBS ROS fixed-pie direction check FAILs at Full PPR / 8 and
Standard / 10 (VA-7). These checks judge the starter/bench scales in
`buildVorpRows`, which price nothing CBS ROS displays -- CBS ROS uses its own
two-tier leg under option C. The simulated defect signature is 88.2% vs CBS
ROS's genuine 86.8%.

**Options.**
- (A) Demote to warnings (informational) for CBS ROS and Razzball, matching
  ESPN's undisplayed fall-back treatment. The checks still run but do not block.
- (B) Retire them entirely. They guard retired code paths.
- (C) Keep FAIL and widen the band. This risks losing the defect signal.

**Recommendation:** (B). The starter/bench scales the checks judge no longer
price anything displayed for CBS ROS or Razzball. They guard dead code. Retire
and remove the failing test assertions.

---

## Q4. OC-8 revisit: zeros in the Indexed factor basis

**Context.** OC-8 was decided as option A (listed players with a blended DDF
Value, zeros included). The lead flagged it as "revisit if Jeremy wants" since
Jeremy found the question unclear. Currently implemented: a player whose DDF
Value is 0.0 counts in the Indexed factor denominator.

**Options.**
- (A) Confirm: zeros included (current). A chart that prices a player another
  chart does not is not penalized in the factor.
- (B) Exclude zeros. Charts with deeper coverage get a higher factor.

**Recommendation:** Confirm (A). It prevents systematic bias against charts
with deeper coverage.

---

## Q5. GAP-VALUECHECK-REFERENCE-AHEAD: accept the reference-ahead state?

**Context.** PR 557 (JEG-560) moved the Python reference to the roster
convention (market-bench seats, midpoint starter line), but the JS engine
still uses the old rules. `value_check compare` disagrees on every source.
JEG-560 follow-up will migrate the JS engine.

This is not a question -- it is a status note. The fix is already planned
(JEG-560). No decision needed.

---

## Verdicts on every carried item

| Item | Verdict | Evidence |
| --- | --- | --- |
| MR-13 (deploy gate) | **Confirm: already live.** `test_view_invariants` (3 views x 17 settings), `test_ddf_composite_value`, `test_rank_guard` are all in `make validate`'s test-core. `fixedPieDiagnostics` and `viewInvariantsDiagnostics` gate every source's Adjusted and VORP totals and each chart's Indexed factor. Broken engines (unscaled VORP, capped Adjusted, wrong factor) fail `test_guard_fails_on_broken_engines`. | Makefile lines 449, 485, 495; curve-widget.js:3140-3217; tests/test_view_invariants.py:207-237 |
| MR-14 (consumers) | **Confirm: correct.** The disagreement spread excludes VORP vs waivers series and published charts when VORP view is active (curve-widget.js:475-484). Trade targets read the Adjusted view's values, which are on the same scale by construction (VP-5). DDF Value is the equal-weight mean of Adjusted values only. | curve-widget.js:479-484 |
| MR-20 (per-game basis) | **Confirm: implemented.** JEG-535 landed (commit 921694cb). ESPN uses `espn_expected_games` (count of non-zero ROS weeks) as the per-game-played denominator. CBS and Razzball stay as-is. `espn_projected_games` is emitted from the ESPN pull. | pipelines/pull_espn_projections.py:540-661; pipelines/bake_players.py:470-478, 937-942 |
| MR-21 (option value) | **Confirm parked.** Needs weekly projections (JEG-540). Post-M4. | wave-plan-2026-10-12.md line 153 |
| MR-22 (bench value) | **Confirm parked.** Needs weekly projections and horizon term. Post-M4. | wave-plan-2026-10-12.md line 154 |
| MR-23 (matchups) | **Confirm parked.** Needs weekly projections. Post-M4. | wave-plan-2026-10-12.md line 158 |
| MR-24 (more seasons) | **Confirm: implemented.** 2015-2025 nflverse data pooled. `derive_lineup_parameters.py` pools all seasons with recency weights. | config/lineup_parameters.json (m values); derive_lineup_parameters.py:133, 783 |
| MR-25 (RB health) | **Confirm: implemented.** Recency weight with 5-season half-life is the default (`injury_history: "recent"`). All-seasons-equal is the alternative (`"all"`). RB m_recent=0.1443 vs m_all=0.1529. | config/lineup_parameters.json:107; derive_lineup_parameters.py:284-288 |
| MR-26 (handcuff) | **Confirm parked.** Needs injury probability data. Post-M4. | wave-plan-2026-10-12.md line 156 |
| MR-27 (bench reasons) | **Confirm: informational.** Coverage table in the agenda is accurate against the current code. No code change needed. | math-review-agenda.md MR-27 |
| OC-8 (zeros in basis) | **Confirm: implemented as option A.** `vpFinite(d)` returns true for 0, so zeros count in the Indexed factor. See Q4 above. | value-model.js:1446-1452 |
| VA-1 to VA-5 | **Resolved.** The VP spec (VP-5, VP-6.4) makes all three invariants exact. `viewInvariantsDiagnostics` measures them at every rebuild. `test_view_invariants` gates them. The old measurements in VA-1 through VA-5 describe retired behavior. | value-model.js VP-5/VP-6.4; tests/test_view_invariants.py |
| VA-6 (CBS ROS/Razzball in Adjusted) | **Resolved.** Under VP-5 every source's Adjusted values sum to the fixed pie. CBS ROS and Razzball are re-weighted like every other source. | value-model.js VP-5 |
| VA-7 (CBS ROS direction checks) | **Needs decision.** See Q3 above. | risk-register.md GAP-CBSROS-DIRECTION-RED |
| GAP-ADJ-CLIP-ZERO | **Closed: moot.** The fit and `buildLiveAdjustedMap` cells are retired (PR 532). The `*_adjusted` keys are deprecated aliases carrying Adjusted values (no clip). | curve-widget.js:96-100 |
| GAP-ADJ-IDENTITY-FALLBACK-UNLABELLED | **Closed: moot.** See Q2 above. | Same |
| GAP-FIXEDPIE-SKIPS-PUBLISHED | **Resolved.** `fixedPieDiagnostics` now checks every source including published charts. The Indexed factor (VP-6.4) makes their totals match by construction. | curve-widget.js:3140-3187 |
| GAP-VIEW-INVARIANTS-MEASURED | **Resolved.** All three invariants hold exactly. Gated by `test_view_invariants`. | Same |
