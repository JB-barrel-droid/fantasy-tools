## 2026-11-02 - JEG-1229 journey envelope caller

Contract: repair the journey harness on main without changing app behavior or value math. Jeremy requested branch `codex/JEG-1229-journey-main-red` and a ready PR; no merge or deploy.

### Verified (check named)
- `python3 -m unittest tests.test_jeg1229_trade_context` reproduced 29 passed / 1 failed with `state.settings` undefined before the fix.
- The fixed harness passed all 30 Node cases in `python3 -m unittest tests.test_jeg1229_trade_context tests.test_uso_site_journey_contract`.
- Repository-wide `rg` found five internal envelope calls in `uso_site_journey_contract.cjs` and one external call in `trade_context_check.cjs`. Only the external call used the wrong signature. It now supplies the optional readout argument and `{state, rowsByKey}`, including the available-source map expected by the helper.
- The combined Python command ran 7 tests: 5 passed, 2 failed. The two USO continuity failures report cross-device basis/source loss. Their helper, app modules and Python tests are unchanged from base `1c04d6fa`; no app fix was attempted.
- Existing positive continuity and negative substituted-roster assertions remain unchanged.

### Claimed, not confirmed
- Independent review and CI are pending. Status: In Review until an independent review.
- No main merge, deploy, Supabase access or credential handling was performed.
