## 2026-11-05 - Week 9 publish unblock: known-case exemption in the waiver band perturbation tests (JEG-1511, part of JEG-1479)

Contract: the rebuild chain's post-rebuild validation (`make validate`) failed on the
Week 9 build in `tests.test_waiver_band_line.OnePlayerPerturbationTest` (both tests),
which held the Week 9 fixture unpublished for ~14 hours. Jeremy ruled (2026-11-05)
that this breach is not enough to stop Week 9 from publishing and the real fix comes
after. This change exempts exactly the three known cases in the two tests (one QB,
two TE — see Verified), prints each whenever the exemption is used, and tracks the
real fix on JEG-1511. Jeremy approved exempting all three on 2026-11-05. No value
math, no published values, and no other assertion change.

Root cause (from the probe below): the 7-player band works as designed — perturbing
the waiver-line player (Kyler Murray, razzball QB, standard/10) by -1.0 moves the
waiver line by exactly 1/7. The breach is in the ES expected-start parts: Murray
crossing below the band shifts the `_expected_start_parts` band edges, every QB's
expected-start parts rise (QB starter group total 20.5 -> 21.64), the QB starter
rate (budget / group total) falls 8.02 -> 7.64, and Josh Allen's Adjusted value
moves ~1.03-1.07 with his own projection unchanged — over the 1.0 bar with no slot
flip. Whether the JEG-1047 bar should bind ES-priced parts, or the parts need
smoothing at the band edges, is the JEG-1511 question; it is a value-model call and
is deliberately not made here.

### Verified (check named)
- Chain status on main (`output/comparison-chain-status.json` at 42304deb): all 7
  sources promoted at Week 9 vintages, `stale_sources: []`, sole failure
  `post_rebuild_validation` with exactly the two perturbation tests named.
- Local reproduction of the CI state: imported all 7 snapshots from Supabase with
  `pipelines/import_supabase_references.py` (vintages match the chain status),
  `projection_identity.py decide` returned bake=true, `bake_players.py` re-baked
  players.json (rz_snapshot 2026-11-04, cbsros_snapshot 2026-11-04).
- Probe (`Setting(standard, 10)` before/after setting player 370 rz_ppg standard
  13.8 -> 12.8): waiver line 13.686 -> 13.543; QB rates and group totals as in the
  root-cause paragraph; largest other-player move Josh Allen -1.027 (slots free).
- Both perturbation tests pass on the committed (Week 8 vintage) data:
  `python3 -m unittest tests.test_waiver_band_line.OnePlayerPerturbationTest...`
  — Ran 2 tests, OK.
- Week 9 baked data, QB case exempted only: both tests fail with exactly two
  further over-bar cases, both the same mechanism in thin 8-team TE pools —
  standard/8 razzball TE key 1970 (Kyle Pitts) -1.0 -> 1.723, and half_ppr/8
  razzball TE key 3279 (Dalton Kincaid) +1.0 -> 1.223; the exempted QB case
  printed 1.027. Those two cases were added to the exemption set with Jeremy's
  approval (2026-11-05).

- Week 9 baked data, all three cases exempted: both tests pass (Ran 2 tests,
  OK), and the only over-bar cases printed are the three exempted ones
  (1.723 / 1.027 / 1.223) — no further cases surface.

### Claimed, not confirmed
- The chain publishes Week 9 on its next run after this lands (to be confirmed
  against `output/comparison-chain-status.json` and the live page).
