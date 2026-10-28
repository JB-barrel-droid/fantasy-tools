## 2026-10-28 — JEG-1134 fallback-font CI follow-up

Contract: monitor the reviewed #1043 head `68b95fa5` to terminal CI and diagnose real failures. Keep this branch isolated; parent requests the final main integration at release time and owns merge/deploy.

### Verified (check named)

- [Preview shard 1, job 122914538827](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/40716224605/job/122914538827) failed the new `test_override_reset_and_undo_keep_the_closed_summary_readable` assertion at 375px. The row was still 45px; its summary was clipped. The prior local pass and independent review of `68b95fa5` did not establish fallback-font behavior.
- A local DejaVu Sans probe reproduced the CI failure: summary text required 243px but had 241px. The same probe passed in the default font and Arial. Extended the existing regression to run both phone widths in the default font and DejaVu Sans; before the CSS fix it fails at `(375, 'DejaVu Sans')`, matching CI. The clipping assertion remains unchanged.
- Tightened the phone gaps beside the summary caret, between the summary/week, and inside the week chip, plus the chip's inline padding. Text stays at 14px and controls retain 44px hit heights. No labels or desktop styles changed.
- After the fix, the same ten targeted tests used in the preceding log pass together: `Ran 10 tests in 62.211s — OK`, no skips. This now includes active/Reset/Undo at 375/390px in both default and DejaVu Sans fonts, Copy link round trips, the collapse mutation and desktop override placement. Command prefix: `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest -v`.
- Additional local 375px DejaVu Sans geometry probe with the short week label set to `Week 18`: Standard, Half PPR and Full PPR summaries all fit without clipping, context height is 45px, and the week button is 76.6 by 44px. Screenshot visually inspected.
- `68b95fa5` CI reached terminal: [render run 40716224637](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/40716224637) passed, and [preview run 40716224605](https://github.com/JB-barrel-droid/fantasy-tools/actions/runs/40716224605) failed only on shard 1's reproduced clipping. Preview build and shards 2/3/4 passed. The follow-up was prepared while those jobs finished, with no intermediate push or main integration.

### Claimed, not confirmed

- The corrected head still requires CI and independent review; the earlier review was for `68b95fa5` only. Parent owns final-main integration and release. No main refresh, merge/deploy, force push or deletion in this follow-up.
