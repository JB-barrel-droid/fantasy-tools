# Delegation Workflow

The repo remains the operating memory and Linear holds the state. The tier
table, rules and merge protocol are in `AGENTS.md` ("Model tiers", "Hot files
and merge order"), copied from the Linear document "Board operating
conventions (2026-10-10)". This file says how a lead uses the lanes. If it
disagrees with `AGENTS.md` or `CLAUDE.md`, they win.

## Lanes (the `Model tier` label)

The label on a ticket is the minimum model. One ticket, one lane.

### T1 deep (`deep-worker`: Opus / Fable, high effort; top GPT / Codex, high reasoning)

- engine and value math, methodology, design
- any bug whose root cause is unknown, until the cause is named
- final review of T2 and T3 output, in a different model from the author
  where possible
- every merge and deploy (Claude lead session only)

OpenRouter / MiniMax models are not allowed in T1.

### T2 build (`worker`: Sonnet; Codex, medium; a strong open model, checked per task)

- implementation against a written spec: pullers, pipeline stages,
  migrations, front end built to a contract line, tests
- executing an approved value spec (a config switch, porting a rule to a second
  path, a fixture refresh), with a T1 review at merge
- escalate to T1 after 2 failed gate runs
- a ticket labelled T2 that needs a judgement call on the numbers is really T1:
  relabel it

### T3 light (Haiku; small GPT; cheap OpenRouter models such as DeepSeek; MiniMax M3 only)

- copy edits, doc moves, research sweeps, scraping and capture, triage, repo
  hygiene, first drafts
- output is untrusted until the gate passes
- never resolves player identity, edits fixtures, or touches `config/` values
- MiniMax M3 is allowed for cheap runs until about 2026-10-31 (Jeremy, 2026-10-26); see `AGENTS.md` "Routing"

### Rules for every lane

- Other model families never merge. Their output is a draft PR on
  `be/<ticket>` or `fe/<ticket>`; the Claude lead re-reads the diff, runs the
  gate and merges.
- Brief with `docs/agent-brief-template.md`. It carries `Touches:`,
  `Model tier:` and the runnable Done-when block.
- Two In Progress tickets may not share a hot file (list in `AGENTS.md`).
  Merge one engine PR at a time, following the merge protocol there.
- The retired `owner:minimax`, `owner:chatgpt`, `owner:muse` and `owner:claude`
  labels and their lanes no longer exist. Ownership is the `Session` label
  (`AGENTS.md`, "Session ownership and takeover").

## When To Delegate

Delegate when one or more are true:

- the task is likely to consume a large context window
- the problem benefits from independent review
- there are multiple architecture/design paths to compare
- debugging requires broad search, logs, or repeated hypotheses
- a pipeline-rules, promotion-path, or fixture-safety change needs a second
  engineering review
- a T3 lane can cheaply gather raw data or visual comparisons that the repo can
  then validate

Do not delegate when the task is a small code/doc edit, a simple command check,
or a local fix the lead can complete faster than writing and reviewing a
handoff.

## Acceptance (Runnable) Convention

Every lane issue carries an `Acceptance (runnable)` section that names the
exact commands a reviewer can paste and re-execute to prove "done". The goal is
that the reviewer's job is checking the evidence, not re-deriving it.

### What the section must contain

- **Tests** — full `python3 -m unittest tests.test_<x>` invocations, in the
  order they must be run. Module names, not descriptions. No "run the tests".
- **Verify scripts** — exact `python3 pipelines/verify_<x>.py` entries with
  any required flags (`--nfl-week`, `--trigger`, `--source`, etc.). Each
  one must exit 0.
- **Rendered / output check** — for UI or published-output changes, the
  command that exercises the artifact a reader actually sees:
  - `node tests/rendered_gate/gate.mjs dist --out output/rendered-gate.json`
    (12-shape Playwright sweep; must exit 0 and report 0 uncaught page
    errors, and, when the issue touches it, DDF pie sums to 100.0 in all 12
    shapes),
  - `python3 verify_live.py tv-YYYYMMDD-HHMM-<sha>` (HTTP 200, build tag
    match, fix markers present in deployed HTML/JS),
  - a headless Playwright capture for one-shot UI checks (e.g. the JEG-45
    pattern in `tests/test_lock_revert_notice_render.py`).
- **Negative-test note** — at least one sentence naming the simulated broken
  state that the regression guard must catch. A guard that asserts current
  behaviour without checking which state is right is worse than no guard
  (CLAUDE.md standing rule).

### Evidence bundle (required to claim done)

A lane may not claim done without attaching all of:

1. The exit code and the last ~20 lines of every `Acceptance (runnable)`
   command's output, pasted in the PR description or commit body.
2. The `verify_live.py` result for any change that affects published bytes
   (build-tag match, fix markers), with the build tag it was checked against.
3. The rendered/output check artifact (the rendered gate's
   `output/rendered-gate.json`, a Playwright text/JSON capture, or a
   `verify_live.py` transcript).
4. A one-line statement of what the negative test against a simulated broken
   state demonstrated (which test failed and on which mutation).

### Rejection language is a copy-paste

When an issue's evidence bundle is missing or incomplete, reject with the
exact missing piece named:

- **Missing tests** — "Acceptance (runnable) does not name which
  `python3 -m unittest` modules run. Paste the module list and the exit
  codes."
- **Missing verify script** — "Acceptance (runnable) does not name the
  `python3 pipelines/verify_<x>.py` command(s) and flags. Paste them."
- **Missing rendered check** — "Acceptance (runnable) does not name the
  rendered/output command. Paste `node tests/rendered_gate/gate.mjs dist`
  (or equivalent) and its exit code."
- **Missing negative-test proof** — "Acceptance (runnable) does not show the
  regression guard catches the bug it names. Add a sentence naming the
  simulated broken state and which test fails on it."
- **Missing evidence bundle** — "PR/commit does not paste exit codes and the
  last ~20 lines for each Acceptance (runnable) command. Paste them or this
  cannot be reviewed."

Out of scope: changing what "done" means for methodology, copy, or publish
(still the human's gate). A passing evidence bundle proves the engine
worked; it does not approve publishing.

```text
Ticket: JEG-___ (team Jegabee)
Model tier: T1 | T2 | T3
Touches: <hot files from AGENTS.md, or "none">
Repo: fantasy-tools
Branch/status: <be/<ticket> or fe/<ticket>, important uncommitted files, latest relevant commit>

Task:
<one concrete question or investigation>

Context:
- <files/docs to read first>
- <project rules that matter, especially fail-closed data rules>
- <known commands, failures, or observations>

Acceptance (runnable):
- Tests: <exact `python3 -m unittest tests.test_<x>` modules, in order, that must exit 0>
- Verify scripts: <exact `python3 pipelines/verify_<x>.py --...` entries, in order, that must exit 0>
- Rendered/output check: <exact command(s) that exercise the published artifact, e.g.
  `node tests/rendered_gate/gate.mjs dist --out output/rendered-gate.json`,
  `python3 verify_live.py tv-YYYYMMDD-HHMM-<sha>`, or a headless Playwright capture>
- Evidence bundle: paste the exit codes and the last ~20 lines of each command's output
  in the PR description or commit message; a lane may not claim done without them.

Please do:
- <expected output shape: findings, options, patch plan, debug trace>
- include file/line references where relevant
- call out tests or validation needed

Please do not:
- <for review tasks: do not edit files>
- <boundaries, e.g. do not write under data/ or dist/>
```

## T3 Capture Handoff Template

```text
Goal:
<raw capture, comparison, research sweep, or prototype exploration>

Inputs:
- <source URLs, dashboard links, files, current vintage/week>
- <required scoring/teams/source labels>

Output wanted:
- <CSV/JSON/table/screenshots/observations>
- <required columns or fields>
- <timestamp/content-vintage expectations>

Boundaries:
- collect facts only; do not decide canonical player identity
- do not zero-fill missing values
- preserve raw source labels and timestamps
- note failures, captchas, stale content, or uncertain matches
```

## Integration Checklist

Before accepting delegated output:

1. Re-read the touched files or artifacts locally.
2. Check the output against `docs/pipeline-rules.md`.
3. Convert raw T3 output through the documented repo pipeline before using it.
4. Add or update tests when behavior changes.
5. Run the smallest meaningful validation command, then `make validate` for
   publishable or promotion-adjacent changes.
6. Review T2/T3 work at T1, then merge per the merge protocol in `AGENTS.md`.
7. Commit and push a coherent slice, or leave a handoff note clear enough for a
   new harness to resume within 10-20 minutes.

## Anti-Patterns

- Do not ask a T3 lane to match player identities, triage `review_rows`, edit
  fixtures, touch `config/` values, or decide promotion readiness.
- Do not let another model family push to `main`, merge, or trigger deployment.
- Do not switch harnesses in the middle of a candidate/promotion path without
  recording the exact artifact paths and next command.
- Do not treat any uncommitted chat conclusion as a project rule. Durable rules
  belong in committed docs.
- Do not parallelize dependent pipeline stages. Each stage gates the next.
- Do not run two In Progress tickets on the same hot file.

## Continuity Notes

Every meaningful handoff should include:

- current branch and latest commit
- files changed
- commands run and results
- unresolved failures or review rows
- next recommended action

The goal is not ceremony. The goal is to keep work portable across Claude
sessions, other model families, local shell work, and GitHub without losing the
thread.
