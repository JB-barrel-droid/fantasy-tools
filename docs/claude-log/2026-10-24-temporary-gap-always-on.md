# Temporary lineup gap flag was set on every offer

**Date:** 2026-10-24

## What happened
After deploying the MCP tools, a live `find_trades` call showed the "temporary lineup gap" warning on every
offer, including offers between full, healthy rosters. In `mcp/viability.ts` the other team's gap was checked on
`theirAfter`, whose rows have no `_market` value (only `theirAfterM` does), so no player counted and every
slot looked empty. The flag only shows as a warning (it does not change `viable`), but it was wrong on every offer.

## Changed
- Check the other team's gap on `theirAfterM`.
- Two tests in `tests/node/viability_check.mjs`: false for healthy complete rosters; true when their only QB is out.

## Verified
- Negative test: with the old line restored, the healthy-rosters test fails (27 pass, 1 fail); with the fix, 28 of 28 pass.
- Reproduced on the deployed function before the fix (gap shown on 5 of 5 offers).

## Not verified
- The deployed function still has the old behavior until it is redeployed.
