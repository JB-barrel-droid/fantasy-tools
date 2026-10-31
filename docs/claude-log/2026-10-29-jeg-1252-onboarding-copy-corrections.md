## 2026-10-29 - JEG-1252 onboarding copy corrections (PR #1078, JEG-1223)

Contract: correct the four user-facing overpromises Codex's review found in the JEG-1223 copy pack (head 727b67b), with evidence and focused claim checks. Docs and one docs-only test; no runtime code, deploy or Supabase.

### Verified (check named)
- Every connector tool's `site_url` content read from `supabase/functions/mcp/state.ts` `finish()` and the `work` each tool passes in `tools.ts` on `origin/main` b863069; `git diff 021c5bf origin/main -- supabase/functions/mcp` is empty.
- Live DDF connector calls (agent session, not a consumer client), 2026-10-29 about 15:50 UTC, values dated 2026-10-29: `find_trades` link carries `mine` and `theirs`; `find_trades_league` link carries `mine` only (two opponents passed); `get_values` link opens `#trade-targets` with settings only.
- `python3 -m unittest tests.test_jeg1223_onboarding_copy`: 8 tests pass on the corrected doc. Run against the 727b67b doc, its checks flag `ai.body`, `ai.cta.note`, `ai.next.note`, `ai.link.more`, `ai.err.notconnected` and `ai.err.busy`.

### Claimed, not confirmed
- The state-codec fallback (link with no settings or players) is read from source, not seen live.
- No Claude or ChatGPT consumer-client test of connect, ask or link round trip was performed.
- The new test is not wired into a Makefile target or CI shard.
