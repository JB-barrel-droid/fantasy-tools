## 2026-11-03 - site builder shared alias contract / JEG-1419

Contract: continue local validation from the first unrun test-core command on
`18a8be81`, without duplicating the previous broad run. Preserve fixtures and
leave denied PR/Linear metadata updates untouched.

### Verified (check named)

- Resumed test-core at `tests.test_isolate_post_validate` using exact Makefile
  commands. Sixteen completed unittest groups passed (155 tests), including
  rank-guard, source integrity, superflex, publisher values, both two-QB suites,
  CBS ROS bake identity and suffix identity. The original CBS readiness timeout
  did not recur. Log: `/tmp/jeg-1419-remaining-validation.log`.
- The next group, `tests.test_player_aliases`, failed one of 14 tests:
  `NoPrivateAliasList.test_only_lib_player_aliases_reads_the_list_and_nobody_reads_alias_to_canonical_privately`.
  It identified `pipelines/build_site_waiver_boards.py` independently naming the
  alias JSON path, outside the shared alias contract.
- The site builder now derives that path from `build_weekly_inputs.ALIAS_FILE`
  and reroots its repository-relative path for offline replay roots. The shared
  module remains the single path owner and the producer remains its reader.
  No producer, identity resolver, fixture, assertion or timeout was changed.
- After the fix, `python3 -m unittest tests.test_player_aliases` passed all
  14 tests in 6.300s. Log: `/tmp/jeg-1419-alias-guard.log`.
- `python3 -m unittest tests.test_site_waiver_boards` passed in 148.241s:
  all 24 settings, valid boards and hashes, disabled missing weekly data,
  deterministic rerun bytes, and clean next-week recovery retaining prior
  board, manifest and gzip bytes. Log: `/tmp/jeg-1419-site-after-alias.log`.
- `git diff --quiet HEAD -- tests/fixtures` passes: all fixture bytes are
  unchanged from the corrected, committed `18a8be81` head.

### Claimed, not confirmed

- The rest of test-core after `tests.test_player_aliases`, strict value parity,
  integration and `tests.test_v2_contract_render` remain pending. No complete
  green make-validate or full current-head CI receipt is claimed.
- The PR is still draft. Its independent-review floor remains high-risk due
  to the earlier fixture correction. PR body and Linear fields remain untouched.
