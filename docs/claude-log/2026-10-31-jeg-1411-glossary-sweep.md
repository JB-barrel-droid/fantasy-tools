## 2026-10-31 - Outside-site glossary / JEG-1411

Contract: apply settled JEG-1212 copy only in an isolated worktree. No value math, identifiers, data, merge or deployment changes.

### Verified (check named)
- Read JEG-1411 and its Muse finding; re-read quoted source on fetched origin/main f58091a3909c3a53f1e9eae7fb413355efc1dead before editing.
- `gh pr list --state open` plus `git ls-remote --heads`: posts 04–06 are owned by #1076 / claude/JEG-545-research-posts (JEG-1257). Skipped them; post 02 remains with #982. JEG-1408 is explicitly read-only.
- `GLOSSARY_REF=origin/main python3 -m unittest tests.test_glossary_outside_site`: fails (20 subtest failures) before changes.
- `python3 -m unittest tests.test_glossary_outside_site tests.test_mcp_remote`: 8 tests pass after changes. Updated one existing connector assertion because Jeremy changed its pinned definition, not its behavior.
- `make validate`: FAIL during sync: missing Playwright chromium_headless_shell-1208. Later gate stages were not reached. Generated churn restored; generated untracked artifacts remain local and are excluded from the commit. No dist files edited by hand or committed.
- `git diff --check`: passes. No Deno tests are present in supabase/functions/mcp; used the repository Node-backed connector suite.
- Server card and connection guide are already clean; no edits needed. Historical research context outside the posts is not rewritten.

### Claimed, not confirmed
- Full validation remains blocked by the missing local browser; no passing full gate or live behavior is claimed.
- F8/F9 generated copies must be refreshed by a successful build; the source wording is corrected here.
- Posts 04–06 need their owner to apply F12–F14. F6 (Market consensus vs Trade chart median) and F18 (Rescaled vs Indexed) remain open for Jeremy.
- Connector copy goes live only at the next mcp deploy (JEG-1400), requiring Jeremy's explicit yes. No deployment or Supabase write performed.
