# Delegation Workflow

This project can use several AI tools, but the repo remains the operating memory
and ChatGPT/Codex remains the hub. Delegate expensive thinking; integrate
deliberately.

## Roles

### ChatGPT/Codex

- frames the task and decides whether delegation is worth it
- supplies repo context, constraints, and success criteria
- reviews Claude/Muse output before acting on it
- makes final product and architecture decisions
- edits, validates, commits, pushes, and records durable handoffs

### Claude Code MCP

Best for token-heavy engineering work:

- architecture/design exploration
- code review and risk finding
- debugging investigations
- broad repo search and subsystem summarization
- migration plans that need careful tradeoff analysis

Claude output is advisory until ChatGPT/Codex verifies it against the repo.

### Muse.ai / Muse

Best for abundant-usage work with concrete output:

- raw source scraping or capture
- current Muse reference-dashboard comparison
- visual/design exploration
- quick prototype sketches
- research sweeps and observation lists

Muse output should usually become a raw input, artifact, or recommendation. It
should not become runtime infrastructure or the only copy of an implementation
detail.

## When To Delegate

Delegate when one or more are true:

- the task is likely to consume a large context window
- the problem benefits from independent review
- there are multiple architecture/design paths to compare
- debugging requires broad search, logs, or repeated hypotheses
- a pipeline-rules, promotion-path, or fixture-safety change needs a second
  engineering review
- Muse can cheaply gather raw data or visual comparisons that the repo can then
  validate

Do not delegate when the task is a small code/doc edit, a simple command check,
or a local fix that ChatGPT/Codex can complete faster than writing and reviewing
a handoff.

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
Repo: fantasy-tools
Branch/status: <branch, important uncommitted files, latest relevant commit>

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

## Muse Handoff Template

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
3. Convert raw Muse output through the documented repo pipeline before using it.
4. Add or update tests when behavior changes.
5. Run the smallest meaningful validation command, then `make validate` for
   publishable or promotion-adjacent changes.
6. Commit and push a coherent slice, or leave a handoff note clear enough for a
   new harness to resume within 10-20 minutes.

## Anti-Patterns

- Do not ask Muse to match player identities, triage `review_rows`, edit
  fixtures, or decide promotion readiness.
- Do not let Claude Code push to `main` or trigger deployment without
  ChatGPT/Codex or human review.
- Do not switch harnesses in the middle of a candidate/promotion path without
  recording the exact artifact paths and next command.
- Do not treat any uncommitted chat conclusion as a project rule. Durable rules
  belong in committed docs.
- Do not parallelize dependent pipeline stages. Each stage gates the next.

## Continuity Notes

Every meaningful handoff should include:

- current branch and latest commit
- files changed
- commands run and results
- unresolved failures or review rows
- next recommended action

The goal is not ceremony. The goal is to keep work portable across ChatGPT/Codex,
Claude Code MCP, Muse, local shell work, and GitHub without losing the thread.

## Owner Labels (Linear, 2026-10-01)

Issue ownership across agents is tracked with Linear labels — there is no
Claude or ChatGPT user in the workspace, so assignment runs through
label + status/priority + comment, which each lane reads:

- `owner:muse` — Roman's lane: PM, review, all merges, validation, deploys,
  rendered production QA.
- `owner:claude` — Claude Code's lane: works issue branches, opens draft PRs,
  never merges/deploys. Current batch: JEG-23 + JEG-44 (in progress),
  JEG-21/JEG-22/JEG-24 caption batch (todo), JEG-8 (rebuild chain).
- `owner:chatgpt` — ChatGPT's lane: works issue branches, opens draft PRs,
  never merges/deploys. Current batch: JEG-17 (full rendered QA),
  JEG-29 (guard harness rebuild), JEG-45 (silent lock-revert notice).

Roman assigns via label + comment, reviews every PR for methodology
regressions, merges in lane order, validates, deploys, and verifies Pages +
rendered production after every deploy.
