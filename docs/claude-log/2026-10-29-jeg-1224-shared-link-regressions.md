## 2026-10-29 - JEG-1224 shared-link value basis and override loss

Contract: a reproducible bug and contract packet for value basis and override fidelity across
Copy link, Compare/finder/league links, MCP read_state and the link back to the site, with
failing-before specs and an integration plan for Codex. No production code, existing test or
active PR branch changed.

### Verified (check named)
- `node --experimental-strip-types --no-warnings tests/jeg-1224/shared_link_regressions.mjs`
  on main `021c5bfd` (2026-10-29 01:37 UTC): 20 cases, 14 failing specs, 6 passing guards,
  0 differ from the record; exit 0. `--strict`: exit 1 (specs still failing, as intended).
- Executed findings: codec drops basis/ov/valuecontext with no warning (C1-C3); overflow
  Copy link omits them on all three trade tabs (L1-L4); Compare links merge the sender's
  overrides into the reader's and miss the explicit default (O1, O2); a malformed complete
  link is skipped silently (O7); unpriced overrides are counted (O8); read_state and the
  link back lose the value context (M1-M3, stub get-values).

### Claimed, not confirmed
- S1 to S3 (v2.js readTradeHash routing order, Trade targets links never applying the
  context, reopen after "Use our methodology") are from source reading only.
- Not checked against the live site, the deployed mcp function or a real chat client:
  github.io is blocked from this environment.

### Update: decisions recorded (same PR)
- Jeremy's calls, relayed with his words attached: D1 "B" (chat prices under the link's basis
  and overrides, JEG-1225), D2 "A" (Compare links use only the sender's settings), D3 "A"
  (overflow Copy link carries the value context). README plan slices 3 and 4 updated; harness
  case M1 now specs pricing under the override (58, not 40). Rerun: 20 cases, 14 failing specs,
  6 guards, 0 differ from the record.
