## 2026-10-27 - JEG-1082 targets and names render tests green again (session:cma)

Contract: finish PR #978 (Ba-Nana's targets fold CSS; Jeremy 2026-10-27: "Merge"). Main was merged in, and both render files were red in the sandbox for a new reason: since the Tuesday week flip the page excluded every chart as not yet published, so Targets had no rows and Compare had no nets. Both tests now pin the page clock to the data's week, the same JEG-1152 pin the other render tests already use (`_render_env.pin_data_week_script()`). No assertion changed.

### Verified (check named)
- `python3 -m unittest tests.test_v2_targets_render`: before the pin, it failed with "the engine gives no targets" at every viewport. With the pin and #978's CSS, OK (2 tests).
- `python3 -m unittest tests.test_v2_names_render`: before the pin, it failed with "[compare] 0 nets in the deal read". The mutation guard ("definition changed") was already caught. With the pin, OK.
- `python3 -m unittest tests.test_v2_contract_render`: OK on the merged branch.

### Claimed, not confirmed
- The 1366x768 fold numbers in Ba-Nana's 2026-10-26 entry (5th row ends at 1020px) were not re-measured here. The test's fold check passing is what was checked.
