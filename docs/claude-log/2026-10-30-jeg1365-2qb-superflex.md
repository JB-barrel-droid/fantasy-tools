## 2026-10-30 - JEG-1365: 2QB leagues use superflex values

Contract: price a league that starts 2 QBs (no superflex slot) with the published charts' own superflex / 2-QB values on the page, in the Python reference and in the connector's endpoint, so the connector's explain text becomes true (Jeremy 2026-10-29, audit decision 9 A: "A for now, but back ticket to actually use the value replacement and starter bench logic here"; follow-up JEG-1366).

### Verified (check named)
- One rule on three paths: `ValueModel.usesSuperflexValues`, `value_reference.uses_superflex_values`, `pipeline.ts usesSuperflexValues` give the same answer for QB 2, QB 3, SF 1 and the default roster (`tests/test_jeg1365_two_qb_superflex_values.py Rule`).
- At ppr/12/QB2 each chart with a superflex list (FantasyCalc, CBS, FantasyPros, USA Today) contributes the same natives as at ppr/12/SF1, in the reference and in the endpoint's own input (`ReferenceNatives`, `EndpointNatives`, runner `--dump-natives`). 6 of the 8 tests fail on origin/main b3eb8d9 (run in a worktree of main with the same test file).
- The endpoint equals the Python reference at ppr/12/QB2 (max difference 0.0) after the change, and also before it (`EndpointNatives.test_endpoint_equals_reference_in_a_two_qb_league`).
- No movement outside 2-QB leagues: ppr/12 1-QB and ppr/12 superflex, 0 values moved on the endpoint runner and on the reference, before vs after.
- ppr/12/QB2: 201 players' DDF Values moved (fresh `make sync` build of the 2026-10-30 fixture). QB pool 584.1 -> 824.0; RB 976.0 -> 850.5; WR 952.3 -> 853.5; TE 175.5 -> 160.0.
- `tests.test_two_qb_direction.ReferenceDirection` still passes (2-QB top QB >= 1.08 x 1-QB at all 12 combos).

### Claimed, not confirmed
- The page itself at QB 2 (Playwright is not available in this cloud session): `tests/test_endpoint_parity.py` custom league `roster_and_shares` (QB 2) and `tests/test_superflex_publisher_values.py` EngineOverlay run in CI.
- Live connector answers change only after get-values is redeployed (Jeremy's yes); the page changes on the next Pages deploy after merge.
