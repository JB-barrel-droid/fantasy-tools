## 2026-10-23 - Docs vs code staleness fixes (JEG-975)

Contract: bring six docs back in line with `origin/main` 161461b4 after the 2026-10-22 audit: the v2 mobile plan, the risk register, the v2 design notes, the methodology status block and the two indexes. Docs only. Out of scope by instruction: bench share, bench seats, the promotion model and the DDF source list (PR #867 and lane D rewrite those), and `docs/feature-contract.md` (mirror of a Google Doc). Branch `be/JEG-975`.

### Verified (check named)
- Mobile plan paths: `ls app/v2` shows `v2.css`, `v2.js`, `shell.html`; `app/trade-value-chart/v2/` does not exist. Nav labels from `grep data-view app/v2/shell.html` (seven tabs: Writing, Player values, Trade targets, Risers & fallers, Compare a trade, Find a trade, Values auditing). Phase 1 is not on main: no `tests/test_v2_mobile_phase1_render.py` on `origin/main`, and PR #853 is open (`mcp__github__list_pull_requests`). Phase 2 nav is merged: `git show --stat 161461b4` (#864) and the "JEG-953 hamburger navigation" block in `app/v2/v2.css`.
- PR states by `mcp__github__pull_request_read`: #803, #823, #824 merged. #848 merged (`git log origin/main`, 40813a7b). Open now: #845 (draft), #853, #856, #860, #866, #867, #868, #837.
- Linear states by `get_issue`: JEG-868, 869, 871, 872, 873 Done; JEG-877 still reads In Review.
- GAP-VALUECHECK-REFERENCE-AHEAD: read `runbooks/sweep-and-rank-guard.md` section 3 ("cleared", `agree`, 715,584 values at e71e8262), `Makefile` (`validate` includes `value-check-compare`, `--strict`), and `docs/claude-log/2026-10-22-jeg-804-ddf-projections-only.md` (`agree`, 1,224,171 values). Row moved to Fixed Or Controlled.
- JEG-879 / JEG-881 guards: `git log origin/main -- tests/test_v2_finder.py` shows #863 "restore loosened guards"; `grep 'r2 = run' tests/test_v2_finder.py` finds nothing; `tests/test_v2_finder_render.py` asserts `heldNames` is non-empty.
- Index gaps: a shell loop over `docs/*.md` against `docs/README.md` and `docs/research/*.md` against `docs/research/README.md` found six unindexed docs and five unindexed research pages before the edit.

### Claimed, not confirmed
- No value_check, test or build was run (docs-only; `make sync` and live checks were excluded). The "agree" statements are read from the runbook, the Makefile and earlier logs, not re-run today.
- JEG-877: Jeremy's acceptance of 1080 px (2026-10-23) is taken from the ticket brief; the Linear ticket still reads In Review and its comment was not read. The test comment block in `tests/test_v2_targets_render.py` still says the 1060 value was awaiting Jeremy; left alone (test file).
- Owner and Verified cells for the new index rows: only the mobile plan (JEG-927, 2026-10-23) is set; the others are `unknown` or `-` rather than guessed.
- Two bench-share research pages (`bench-share-bounds.md`, `bench-share-decomposition.md`) are still unindexed on purpose (lane A rewrites them).
- Log policy (CLAUDE.md says no session log is required; the log README and `docs/README.md` say entries go in `docs/claude-log/`) is not changed here. It is Jeremy's call; posted on JEG-975.
