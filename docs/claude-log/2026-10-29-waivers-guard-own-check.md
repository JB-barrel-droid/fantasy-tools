## 2026-10-29 - Waivers render guard counts a mutant only on its own check (JEG-1282, #1149)

Contract: `test_guard_fails_on_broken_builds` counted any error or exception as a kill, so two of eight mutants were "caught" only because the harness raised, and a missing browser read as eight catches. Merged as 99be687d; only `tests/test_waivers_render.py` changed.

### Verified (check named, as recorded in the PR #1149 commit message)
- "no aria-sort" now removes the whole `if (S.sort.key === col.id) th.setAttribute("aria-sort", ...);` statement; removing only the call left the `if` guarding the header-button block.
- The verdict check ranks only known verdicts and returns its "verdict cells" diagnostic instead of raising ValueError.
- No `except Exception` in the guard; each mutant names the check that must catch it (`CAUGHT_BY`), and another check's line is not a catch. The `broken` table keeps its 3-tuple shape for #1144's reader.
- Real Google Chrome via `CHROMIUM_PATH`, `RENDER_TESTS_REQUIRED=1`, viewports 1366x768 and 390x844: guard OK; every mutant's `run_checks` returned a list containing its own check's line, none raised. `test_tab` baseline OK at four viewports; offline rule test OK.
- With `CHROMIUM_PATH` at a non-executable file: 8 subtest errors under REQUIRED=1, 8 skips without it.

### Claimed, not confirmed
- CI's preview run behaving the same was not run locally.
