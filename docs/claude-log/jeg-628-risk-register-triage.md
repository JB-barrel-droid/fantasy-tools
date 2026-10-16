# JEG-628: risk register rows with no owner ticket

**Date:** 2026-10-15
**Ticket:** JEG-628
**PR:** this PR

## What changed (docs only, `docs/risk-register.md`)

- Closed with a reason: GAP-008, GAP-017, GAP-CBSROS-ROW-CAP-TIES, GAP-USAT-FIRECRAWL (both rows), GAP-MISSING-SECTION-REFUSES-RENDER (both rows) as won't fix; GAP-FANTASYCALC-TERMS deferred (no legal/ToS work pre-launch); GAP-018 (`make preview-local` exists), GAP-CONSOL-CAP (constraint dropped by jeg482 migration), GAP-USAT-CI-BLOCKED (relay works).
- GAP-FC-COV is still live (chain status 2026-10-16T01:02Z: FantasyCalc held on WR coverage 76 < 79). New owner ticket JEG-667.
- Ticket Index updated.

## Verified vs claimed

- Verified by reading: Makefile `preview-local`, jeg482 migration, chain status file, sbclient usage in repo.
- Claimed, not re-run: relay health beyond the chain status "usatoday: promoted 3/3".
- JEG-629 was already Done (PR #572); nothing to do.
