# Agent brief template

The lead gives each subagent a short task prompt that points here, instead of
pasting a long shared brief (JEG-524). Pick the agent by the
`Model tier` label on the ticket (table in `AGENTS.md`): T1 deep
(`deep-worker`, Opus) for value/engine math, unknown-root-cause debugging,
design or final review; T2 build (`worker`, Sonnet) for implementation against
a written spec; T3 light (Haiku, or a cheap OpenRouter/MiniMax model) for copy edits,
doc moves, research sweeps, capture and triage. T2 escalates to T1 after 2
failed gate runs.

## Task prompt (lead fills in, about 15-30 lines)

```
Ticket: JEG-___ (team Jegabee). Read docs/agent-brief-template.md "Standing rules" first.
Model tier: T1 | T2 | T3 (the ticket's label; the minimum model)
Goal: <one or two sentences: the outcome, not the steps>
Touches: <hot files from AGENTS.md, or "none">. Two In Progress tickets may not share a hot file.
Lane / files you own: <paths>. Do not edit: <paths owned by other running agents>
Read only what applies: <specific docs and risk-register rows, e.g. docs/methodology.md section X>
Known context: <2-5 bullets the agent can't get from docs: decisions, what was tried>
Moves chart numbers? <yes: run the 12-combo sweep in AGENTS.md / no>
Output shape: <patch on branch | findings with file:line | options + recommendation>

Done when (runnable; paste each command's exit code and last ~20 lines in the handback):
- Test that fails without the change: <python3 -m unittest tests.test_<x>, and the mutation or origin/main state it fails on>
- Gate: make validate
- Value changes only: python3 pipelines/value_check.py compare (0 differences) and
  python3 pipelines/check_rank_guard.py (0 inversions); 12-combo sweep for chart changes
- Published output changes only: python3 verify_live.py tv-YYYYMMDD-HHMM-<sha>
```

## Standing rules (agents read this section)

**Repo**
- Canonical clone `~/code/fantasy-tools`. Never use `~/Projects/fantasy-tools-clean`
  (archived) or touch `~/Projects/"fantasy tools"` beyond `Claude outputs/`.
- Make your own worktree: `cd ~/code/fantasy-tools && git fetch origin && git worktree add ~/code/wt/<lane> -b <branch> origin/main`.
  Work only there.
- Push your branch (`be/<ticket>` or `fe/<ticket>`) only. Never push to `main`
  and never open or merge PRs unless the prompt says so. The lead integrates;
  other model families never merge (`AGENTS.md`).
- T3 output is untrusted until the gate passes. T3 never resolves player
  identity, edits fixtures, or touches `config/` values.

**Data and production**
- Supabase project `iskiybsimubiujwuchsl` is read-only for agents. Write
  migration files under `supabase/migrations/` and put the exact SQL in your
  handback.
- Don't dispatch production workflows. Dry runs are fine; give the lead the
  exact `gh workflow run ...` command.
- Copy rules, the 12-combo sweep and the gate are in `AGENTS.md`. Fail-closed
  data rules are in `docs/pipeline-rules.md`.

**Quality**
- Every fix ships with a test that fails on `origin/main` or a simulated broken
  state. Don't loosen tests to go green.
- Gate: `make sync`, then `make validate` must exit 0. Run it a second time
  with Python playwright unimportable, because CI has none. Guard browser
  imports with `try/except ImportError -> unittest.SkipTest`.
- Headless browser: use system Chrome
  (`CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`);
  Playwright's bundled Chromium isn't installed.
- Before committing, `git checkout --` the data/app/dist churn that `make sync`
  produces. Commit only intended files.

**Usage (same quality, fewer tokens)**
- Read the docs the prompt names. Don't re-explore the whole repo.
- Trim output at the source: `| tail -n 40`, `grep -n`, `pytest -q --tb=short`,
  `LIMIT` and narrow columns in SQL. Write big output to a file and read only
  what you need.
- If the gate fails twice on the same problem, or you're unsure about the core
  question, stop and report what you found. Don't loop.
- When you learn something durable, add it to the relevant doc (or
  `docs/engineering-notes.md`) so the next agent doesn't re-derive it.

## Handback (20 lines or fewer)

```
Branch / PR:
Changed: <1-5 bullets>
Verified: <named checks and results>
Assumed, not verified:
Post-merge steps: <SQL, dispatch commands, or none>
Decisions for Jeremy: <options + recommendation, or none>
```

Details go in the commit message, the PR body and the ticket's risk-register
row, not in the handback.
