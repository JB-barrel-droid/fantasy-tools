## 2026-10-31 - JEG-1411 generated glossary copies

Contract: continue draft PR #1252 on `be/jeg-1411-glossary-sweep`; use installed Chrome for validation and commit only intended generated F8/F9 changes plus continuity notes. Supersedes the missing-browser limitation in the earlier glossary-sweep log; that earlier entry remains the historical record.

### Verified (check named)
- `CHROMIUM_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' RENDER_TESTS_REQUIRED=1 make validate`: sync completed using installed Chrome; FAIL in test-core at `test_keyboard_mobile_and_overlap_guard` (selected `''` vs `'beta'`), the known red Jeremy identified as outside this PR. 11 saved-team tests ran, 1 failure. No fix attempted; remaining validate stages not reached.
- `python3 -m unittest tests.test_glossary_outside_site tests.test_mcp_remote`: PASS, 8 tests.
- Direct Python comparison using `build_llm_surfaces.fill`: `dist/llms.txt` and `dist/ddf-skill/SKILL.md` match their source templates after URL substitution and contain the settled DDF Value definition. The generated local ZIP contains the identical skill text; ZIP is not staged.
- F8/F9 regeneration also catches up existing source tool lists and skill guidance; no hand editing of generated copy.

- `git diff --check`: PASS. Only regenerated `dist/llms.txt` and `dist/ddf-skill/SKILL.md` are retained from build output; unrelated tracked generated changes restored, untracked generated artifacts left locally without deleting anything.
- No ENOSPC occurred. `git diff --name-only` confirms no edits to app/v2/v2.js, app/v2/shell.html or posts 02/04/05/06. No value math or data changes committed.

### Claimed, not confirmed
- No live connector check, deployment, merge, Supabase write, credential change or production deletion performed. Connector copy still waits for JEG-1400 and Jeremy's explicit yes.
- Posts 04–06 remain owned by #1076 and post 02 by #982. F6 and F18 remain open for Jeremy; this continuation chooses no names.
