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
