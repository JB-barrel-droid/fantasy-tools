## 2026-10-29 - JEG-1238 corrections JEG-1293 and JEG-1315: references and second hops

Two independent Claude reviews of the injected-resolver guard (#1103) found
callers that reach `projection_capture.cbs_capture_rows` without the guard
seeing a call. Both fixes are in `tests/test_player_identity_guard.py` only;
no pipeline code changed.

### JEG-1293 (commit 45fb71d9, review of #1128 at 62a67ef2)
- Any load of the injection function that is not the `func` of a call fails,
  in every module, pinned callers included: a stored alias, `functools.partial`,
  passing it as an argument, keeping it in a container, a decorator, and
  `getattr(pc, "cbs_capture_rows")`. `from <defining module> import *` counts
  as importing the bare name.
- Tests: `test_stored_or_partial_reference_fails`,
  `test_real_capture_stored_reference_fails`.

### JEG-1315 (delta review of #1103 at 29367e71)
- Importing the function by name outside a pinned caller fails (a re-export
  stops at the first hop).
- A module alias of the defining module may only be used as
  `alias.<plain attribute>`: `m = pc`, `pc.__dict__`, `vars(pc)`,
  `getattr(pc, <any name>)`, `attrgetter(...)(pc)`, `getattr_static(pc, ...)`
  and passing `pc` as an argument fail.
- A package attribute that is not an imported alias (`lib.projection_capture`)
  fails.
- Beyond the review: a module that holds the function or its module (every
  module that imports `projection_capture`, pinned callers included) cannot be
  used to re-export it: `from holder import pc`, `holder.pc.cbs_capture_rows`,
  `from holder import *`, and a rebound holder alias fail. This keeps the
  existing positive control (a pinned caller importing the function by bare
  name) passing while closing re-export through that caller.
- Tests: `test_reexport_and_alias_escapes_fail` (15 synthetic cases and the
  middle-module first hop), `test_real_capture_reexport_probes_fail` (the
  reviewer's probes 1 to 7 against the real `projection_capture.py` and
  `save_cbsros_references.py`, plus the direct-call control and the clean pair).

### Verified (check named)
- Failing before: the two new tests on 29367e71's guard give 24 failures
  (every probe and case, and the first-hop check).
- Passing after: `tests.test_player_identity_guard` 24 OK; with
  `test_cbsros_bake_identity`, `test_identity_case_duplicates`,
  `test_match_identity_keys`, `test_sleeper_identity_layer`,
  `test_suffix_identity` and `test_sheet_oracle_canonical`, 70 OK.
- Each new rule removed on its own turns the new tests red: by-name import 1,
  defining-module alias escape 10, holder re-export import 3, holder attribute 1,
  holder alias escape 1, package attribute 2.
- The real `pipelines/` scan reports 0 issues.

### Claimed, not confirmed
- `make validate` and the full unit suite were not run here; the change is
  test-only. CI on the new head confirms.
- Dynamic `globals()`, `sys.modules`, `importlib` and cross-module
  monkeypatching stay outside this static guard, as before. A holder's module
  alias passed further than one hop (an alias of an alias of a holder) is
  caught only at the first escape, which already fails.
