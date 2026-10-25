## 2026-10-25 - JEG-1084 inputs status strip as one compact line

Contract: make the inputs status strip one slim line (about 28 px) on wide screens so Compare fits 1366x768 again (Jeremy, 2026-10-25, multiple choice: "Shrink the strip to one compact line (Recommended)"). Phones keep the wrapping layout.

### Verified (check named)
- `tests.test_v2_inputs_status_render` (8 tests, green): new test `test_strip_is_one_slim_line_on_desktop_and_does_not_overflow_a_phone` asserts note height <= 30 px and one text line at 1366, both buttons on the line, no horizontal overflow at 390 and buttons >= 32 px. It fails on main with "45 not less than or equal to 30".
- `tests.test_v2_waterfall_render` on main: `test_waterfall_verdict_layout_example` FAILS (the bug); with this change it passes.
- `tests.test_v2_contract_render` (6) and `tests.test_v2_phone_layout_render` (2) green.
- Throwaway merge of PR #918 (JEG-1056) onto this branch: `tests.test_v2_waterfall_render` 4 tests OK, every mutation GUARD CAUGHT, including "no wide verdict column".

### Test assertion changed (the fixture was wrong, not loosened)
- `test_v2_waterfall_render` picked `ddf_value_charts` as the "other" picker series. Since JEG-1073 it has the same numbers and name as `ddf_value`, so the "verdict not DDF" mutation was invisible. It was only "caught" before because the 45 px strip made every build fail the fit check. The pick now skips `ddf_value` and `ddf_value_charts`.

### Claimed, not confirmed
- CI font setup (Inter hidden via fontconfig) was not separately measured; CI runs `v2-render`.
- Real touch devices; phone check is emulation at 390 px.
- `make validate` result: see PR.
