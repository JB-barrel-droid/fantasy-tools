## 2026-10-24 - JEG-1011 Values auditing: Health check page

Contract: replace the Value pie tab with a plain "is anything wrong?" verdict (one row per check, one column) and question-first drill-downs, per the approved spec and Jeremy's six decisions of 2026-10-24, under the iteration contract (changelog in fantasy-tools-selfhost-notes/jeg-1011-values-auditing/changelog.md).

### Verified (check named)
- Thresholds come from the engine after #867, not the spec: `tools/audit_health_dump.py` (week 7 history-built run equals the live engine, `liveMatch` true for all 12 settings) and `tools/audit_health_thresholds.py` (train weeks 5-7, held-out 3-4; limits 17% / 24% / 75%, shifts 6% / 4% / 0%, nothing fires on held-out). Table in docs/health-check-thresholds.md.
- `make -o sync validate` exit 0 on the merged branch (iteration 3); `tests/test_v2_health_check_render.py` 4 pass (5 frozen fixtures, live page at 1366x768 / 390x844 / 360x740 / 320x568, 12-combo sweep, 19 broken-build mutants each caught; the "table cell mark dropped" mutant first slipped through and the check was strengthened).
- `tests/test_audit_pie.py` 41, `test_v2_audit_render.py`, `test_v2_audit_source_render.py` (+2 mutants: Published not normalized, axis not in percent), `test_v2_a11y_batch2_render.py`, `test_v2_plain_copy_render.py`, `test_v2_polish_render.py`, `test_v2_writing_routes_render.py` pass.
- Old hash `#values-auditing/value-pie` rewrites to `#values-auditing/health-check` (live test).
- Strip fits the first screen: 632px of 768 at 1366x768, 795px of 844 at 390x844 (live test).
- Fresh-eyes review by a separate subagent on screenshots and page text: 10/10, all five task questions answerable, verdict DONE.

### Claimed, not confirmed
- `test_v2_mobile_phase1_render` and `test_v2_phone_tap_targets_render` fail on player-values and writing pages (not the audit tab); baseline comparison on origin/main is recorded in the PR.
- Spec's mutation "exactly one flag fires for that source" is read as "every flag names only the perturbed source" (a starter-only change also breaks that source's total).
- Flag limits are loose on purpose (1.5x headroom); a 10% error in one source does not flag, a 20% one does.
