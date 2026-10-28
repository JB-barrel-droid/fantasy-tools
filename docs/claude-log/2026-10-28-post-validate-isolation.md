## 2026-10-28 - Post-validate culprit isolation (JEG-1201) - WIP, stopped early

Contract: when the chain's whole-site `make validate` fails, hold only the sources whose new data broke it (restore their sections and DDF legs to HEAD, mark `validationHold` "chain hold: post-validate ..."), re-run validate once, and publish the rest as `published_with_holds`. Fail closed otherwise.

Stopped on the coordinator's request (usage nearly out). No code is written yet; this commit holds only this note.

### TODO
Done (reading only):
- Read AGENTS.md, rebuild-chain.yml (validate block ~lines 300-335), record_post_rebuild_validation.py, value_check.py (SOURCE_DERIVED, last_published_fixture, apply/release_holds), rebuild_comparison_chain.py (LEG_FILES, _leg_files/_restore_legs, isolate_hold ~536-640, execute_chain, reindex stage), promote_comparison_section.py (~455 drops holds), the three projection section builders, tests/_holds.py.

Left:
1. Write `pipelines/isolate_post_validate.py`: changed_roots (compare sections + `_adjusted` with hold fields stripped, else a fidelity/value-check hold reads as "changed"), culprits (unittest blocks: skip the dash line right after the FAIL/ERROR header, drop traceback frame lines, whole-word aliases longest-first so "CBS rest of season" is not also "cbs"; add series names from value_check.ROOT_OF/DIAG_ROOT as aliases), isolate (sections + `source_validation[root]` back to HEAD, legs via `git show HEAD:` then `_restore_legs`, hold marked like isolate_hold, promotion records newer than `--since` renamed `.rolled-back.json`), status update (held, held_detail, post_validate_isolation, outcome green -> published_with_holds). Exit 3 on decline.
2. Decline when `espn` is a culprit: its legs are the reindex anchor and players.json is baked from its CSV; both already ran on the new data, so restoring the section alone is inconsistent.
3. Wire into rebuild-chain.yml after the first failed validate: isolator, then `make validate` into `output/post-rebuild-validate-2.log`, else record_post_rebuild_validation on the log that applies and exit 1. tests/test_rebuild_chain_workflow.py (~564) and tests/test_value_check.py (~291) read that block; keep the strings they look for.
4. Hold release: the ESPN section builder deep-copies the old section, so a post-validate hold on espn would survive a good run. cbsros/razzball builders write a fresh section, and promote drops holds on charts (a failed chart run is re-held by isolate_hold). Add a release of "chain hold: post-validate" holds per source in execute_chain, before snapshot_source_state.
5. Write `tests/test_isolate_post_validate.py`, add it to the Makefile next to tests.test_record_post_rebuild_validation, then run it and the tests.test_rebuild_chain_* suites.

Risks found so far: make validate stops at the first failing test-core module, so the second validate can show failures the first never reached (that fails closed). Each validate re-syncs dist/ (sync runs inside validate). A restored chart's Indexed values are against HEAD's ESPN leg (the section is held and hidden).

### Verified (check named)
- None. No code was written or run.

### Claimed, not confirmed
- All of the TODO findings above come from reading the code. No test checked them.
