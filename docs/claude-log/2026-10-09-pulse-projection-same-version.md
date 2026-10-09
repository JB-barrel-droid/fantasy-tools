## 2026-10-09 - JEG-480 ESPN red triage: projection difference is red only against the same publisher version

Contract: decide whether the 21:51Z pulse's ESPN red (39 publisher_vs_stored mismatches) was a save/parse
fault or a stale pulse rule, and fix whichever it was with a test that fails on the broken state.

### Verified (check named)
- ESPN's live API (scratch reader using `fidelity_sources/espn.py`, 21:56Z): Pat Bryant 0.00 full-PPR ROS,
  `injuryStatus` INJURY_RESERVE, `lastNewsDate` 2026-10-09T20:17Z (after the 19:25:45Z save); Troy Franklin
  73.57; Lil'Jordan Humphrey 12.74. All three are Denver receivers: one IR move re-spread the targets.
- `espn_season_projections` (Supabase SQL): the 21:52Z save (manual dispatch, run 37996023182) stores
  Franklin 62.07 half / 23.0 rec, Bryant 0, Humphrey 10.34 half: equal to ESPN now. The saver is right.
- `source_probe_state.espn`: acked_fp 8defecd0... at 19:25:49Z (the 19:25 save). `source_probe.run_probe("espn")`
  now: dd81d27d... (identical on two reads 1 min apart). Different content: a publisher edit after the save.
- CBS rest of season: green in the 21:51Z run (1107/1107 publisher = stored, 1107/1107 chart = stored).
- Razzball: amber, not red (publisher stamp 2026-10-09 newer than the 10-08 snapshot, inside 12 h; live
  fingerprint 00ef7e50... differs from the acked 47373595..., consistent with an unsaved update).
- Rule change: `tests/test_fidelity_pulse.py` ProjectionSameVersion (6 tests). Against origin/main's
  fidelity_pulse.py 6 tests fail; mutating the same-version and block branches to amber fails 4
  (including `test_stored_differs_from_the_same_publisher_version_is_red`, the zeroed-on-save fault).
- Workflows: the three projection syncs fingerprint the publisher before reading data on runs the probe did not
  dispatch and ack it. The command was run locally (dd81d27d...). `tests.test_no_failopen_workflows`,
  `tests.test_razzball_sync_ci` and the other workflow-pinning tests pass.
- `make validate` exit 0 under Python 3.12 (CI's version). Under the machine's default Python 3.9,
  `tests.test_razzball_one_save.test_latest_save_rows` fails (3.9 `fromisoformat` rejects `.1` fractions);
  this is local only and was already the case before this change.

### Claimed, not confirmed
- The next manual or scheduled sync acks its fingerprint (`acked_at` moves with the save). Checked after merge.
- ESPN goes amber, not red, on the next pulse if ESPN edits again between saves.
