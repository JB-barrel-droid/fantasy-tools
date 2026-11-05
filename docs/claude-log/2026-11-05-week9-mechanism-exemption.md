## 2026-11-05 - Week 9 publish: mechanism-scoped waiver-band exemption (JEG-1511)

Contract: unblock the Week 9 publication held by the waiver-band perturbation bar, under Jeremy's 2026-11-05 rulings (first three enumerated cases, then "Broader exemption for this mechanism"), without weakening the bar outside the diagnosed mechanism. This entry covers the second PR; PR #1314 (enumerated cases) has its own entry.

### Verified (check named)
- Post-merge chain run 42031325359 failed post-rebuild validation on the same Kyler Murray case in the two scorings #1314 did not name — half-PPR 1.037, PPR 1.014 (job log for job 127268104261, downloaded and grepped: "known over-bar case (JEG-1511): standard/10 razzball QB 370 -1.0: 1.071" printed for the enumerated instance; the two FAIL blocks list exactly the half-PPR/PPR instances). The enumerated set is bake-sensitive: local bake {Kyler standard 1.072, Pitts 1.723, Kincaid 1.223} vs CI bake {Kyler standard 1.071, Kyler half-PPR 1.037, Kyler PPR 1.014}, neither TE case in CI.
- The original JEG-1511 diagnosis (breach triggers when the perturbed player crosses the band) is falsified by the Week 9 data: for standard/10 razzball QB, seat n=18, Kyler 370 at 13.8 PPG; after -1.0 the band window's key set is identical ([697, 2534, 3803, 370, 28, 2236, 4450] before and after) and waiver_band_line moves exactly 1/7 (13.686 -> 13.543), while _worst returns 1.0272 in both slots-held and slots-free modes (direct _worst calls in a diagnostic script). The amplification is in _expected_start_parts' response to the position's shared lines (waiver line, starter line, ES band edges), not in a crossing jump.
- A first implementation keyed on band-membership change failed the Week 9 local run for exactly that reason (FAILED failures=2; the Kyler standard case unexempted) and was discarded before any PR.
- Final implementation, local on the Week 9 bake (fixture copies from the verified local bake, restored afterwards): `python3 -m unittest tests.test_waiver_band_line.OnePlayerPerturbationTest` — OK, 3 tests, 479.5s; exactly the three expected cases printed as mechanism-exempt in each perturbation test (6 prints: Pitts 1.723, Kyler 1.027, Kincaid 1.223, x2 tests). `BandMathTest` + `EndToEndTest` — OK, 7 tests, 20.0s.
- Predicate controls (direct calls): QB 1.5 and TE 2.0 exempt-eligible; QB 2.001, WR 1.5, RB 0.5 rejected.

### Claimed, not confirmed
- That the CI bake's marginal set (including the Kyler half-PPR/PPR instances) falls inside the mechanism signature — inferred from the CI job log values (QB, <= 1.04, same case family) and confirmed only when the post-merge chain run's validation prints its exemptions and publishes.
- Independent review and PR CI: recorded on the PR itself when they land.
