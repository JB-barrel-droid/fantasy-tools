# JEG-601 / JEG-602 / JEG-583: runbook second-session check, design-notes trim

**Date:** 2026-10-15
**Tickets:** JEG-601, JEG-602, JEG-583
**PR:** this PR

## What changed (docs only)

- `runbooks/README.md`: second-session results per runbook. `runbooks/sweep-and-rank-guard.md`: removed the stale known-red note.
- `docs/v2-design-notes.md`: seven dated sections archived to `archive/2026-10-15-docs/v2-design-notes-build-log.md` (1,356 to 1,156 lines). Kept every section that code or tests cite ("Back-end contract: ...", "Which snapshot is a source's week", frame rules).
- `archive/README.md`: entry added.

## Verified vs claimed

- Verified by running: `nfl_week.py` (6), chain status and value-check and pulse reads, `gh run list` (chain and pages), `verify_live.py` (LIVE OK), `make sync`, `check_rank_guard.py` (pass), `engine_dump.py` (13 True), `value_check.py compare --rerun-engine --strict` (agree, 715,584), `ContractMirrorTest` (4 OK). Generated output from `make sync` was discarded.
- Not run: `make import-health` and producer dispatches (credentials / production writes), `make validate`.
- Claimed, not verified: that the archived sections no longer describe live behavior; the tab sections kept may still hold stale detail.
- Observed, not mine: rebuild chain red on 2026-10-16 (week 6; cbs held at review), deploys failing.

## Left for Jeremy (Drive)

See `docs/contract/feature-contract-id-map.md`: GL-09 to JEG-542 in the Google Doc, drop "to build" on CT-02, GL-19, GL-20, GL-21, TT-05, TT-09, add GL-25/26 for JEG-565, and flip repo-as-source.

## Follow-up (JEG-583)

`AGENTS.md` and `CLAUDE.md` now point at `docs/README.md` and `runbooks/README.md`; the index states the 30-day staleness rule. Not verified: that every Maintained page names an owner ticket and a last-verified date (many do not; refresh tickets are the follow-up).
