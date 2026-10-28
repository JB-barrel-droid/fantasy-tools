## 2026-10-28 - Interactive trades release candidate

Contract: Assemble a small user-facing candidate from interactive Compare (JEG-1214), stable before/after lineup presentation (JEG-1216), and Find a trade guardrail settings (JEG-1184). This is a draft integration branch only; the first release's live QA, full CI, and final independent integration review precede any merge or deployment.

### Exact manifest

| Input | Included head | Role |
| --- | --- | --- |
| `origin/main` after merged #1062 | `3b5c94841d9b524c478d1eb05eb61ecb9665b807` | Base and first user-facing release |
| #1066, JEG-1216 | `ed0154c66422005d05d62c79a45c3b91d1ff39f6` | Stable shared lineup rows and expandable bench |
| #1067, JEG-1214 | `7b60ecad1a01d411c8dbce345fd4ce4cec1affd3` | Interactive Compare; contains the #1066 head already |
| #1068, JEG-1184 | `be501b0b296aaf29c662c12c2fcdbf99a39b18a3` | Finder guardrail settings, persistence and links |

`release/interactive-trades-20261028` merges #1067 once, then #1068 once, with no conflicts. #1066 is an ancestor of #1067 and was not picked separately. Original feature PRs remain open; this release does not auto-close them before live verification. The candidate does not include source health, publishing controls, source taxonomy or design proposals, or fill-value math. Existing value calculations and labels remain as each feature branch supplied them.

### Verified (check named)

- `git merge-base --is-ancestor ed0154c6 origin/fe/jeg-1214-interactive-compare` returned 0; the shared helper is already in Compare.
- `CHROMIUM_PATH=/usr/bin/chromium python -m unittest tests.test_interactive_trades_release_render -q` passed. One browser visit checks both loaded rosters, live trade edits, unchanged lineup rows, bench expansion, 2-for-1 spots, Swap then Cancel, external hash and assist trade replacement, saved and linked guardrail settings, and default finder result parity with inactive guardrails.
- `CHROMIUM_PATH=/usr/bin/chromium python -m unittest tests.test_interactive_trades_release_render tests.test_v2_compare_rosters_render tests.test_jeg1216_lineup tests.test_jeg1216_lineup_render tests.test_v2_finder_guardrails tests.test_v2_finder_guardrails_render -q` passed (6 tests).

### Claimed, not confirmed

- Full CI, final independent integration review, and first release live QA are pending. No production merge, deployment, Supabase action, or branch deletion occurred.
