## 2026-10-29 - Waiver board and Bench Churn design concept (JEG-1196, JEG-1197)

Contract: a docs-only design concept for the waiver dashboard (JEG-1196) and Bench Churn (JEG-1197), on Jeremy's instruction via the coordinator. No code, math, config, Supabase or status changes.

### Verified (check named)
- The weekly-input contract (branch `claude/JEG-1227-weekly-inputs-contract`, `docs/weekly-inputs-contract.md`) has no roster %, adds trend, kickoff time or FAAB field: read the doc and grepped `pipelines/build_weekly_inputs.py` on `claude/JEG-1228-weekly-input-producer` for kickoff, roster_pct, percent_owned and faab (no hits).
- `evaluateChain` and `bestChainFromItems` are not in the repo or `archive/`: `rg -l` over the checkout found nothing.
- The value model prices value above waivers, so DDF Value 0 sits on the waiver line: read `app/trade-value-chart/assets/value-model.js` around `esPositionParts`.
- The mock parses as HTML: Python `html.parser` fed the file without error.

### Claimed, not confirmed
- The mock's desktop and 390px phone layouts were not rendered in a browser here (no Chromium in this cloud session). A Mac screenshot would confirm them.
- My reading of the retired Bench Churn windows (After his game, Before the weekend, continuation after misses) comes from the JEG-1197 text only; the artifact itself was not found.

## 2026-10-29 - Follow-up: Jeremy's answers and the objective (JEG-1196, JEG-1197, JEG-1317)

Contract: record Jeremy's three answers, lead the concept with the one objective the questions serve, and file the FAAB conversion as its own decision ticket. Still docs only.

### Verified (check named)
- JEG-1317 filed in Linear with options A/B/C and a recommendation; it blocks JEG-1197 (Linear `save_issue` response).
- The mock still parses as HTML (Python `html.parser`).

### Claimed, not confirmed
- The FAAB options on JEG-1317 are proposals only; none is measured or approved.

## 2026-10-29 - Correction: FAAB out of scope (JEG-1196, JEG-1197)

Contract: Jeremy said "dont' even research it, we aren't ready to approach it" about FAAB. The entry above is superseded where it files JEG-1317; that ticket is canceled and the concept's v1 cost is only the dropped bench player's DDF Value.

### Verified (check named)
- JEG-1317 is Canceled and no longer blocks JEG-1197 (Linear `save_issue` response).
- No FAAB, bid or JEG-1317 mention is left in the concept or mock except the out-of-scope lines (`rg -i "faab|1317|bid"`); the mock parses (Python `html.parser`).
