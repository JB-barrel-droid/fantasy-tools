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
exact commands a reviewer can paste and re-execute to prove "done". The goal
is that the reviewer's job is checking the evidence, not re-deriving it.

A lane may use `pipelines/check_issue_acceptance.py` (JEG-92) to machine-
check the section before opening a PR. The script reads an issue body from
a file path or `--stdin` and exits 0 on pass, 1 on reject, naming the
exact missing piece in the copy-paste language below:

- **Missing section** — "Acceptance (runnable) section is missing."
- **Missing tests** — "Acceptance (runnable) does not name which
  `python3 -m unittest` modules run. Paste the module list and the exit
  codes."
- **Missing verify script** — "Acceptance (runnable) does not name the
  `python3 pipelines/verify_<x>.py` command(s) and flags. Paste them."
- **Missing rendered check** (UI-affecting issues only) — "Acceptance
  (runnable) does not name the rendered/output command. Paste
  `node tests/rendered_gate/gate.mjs dist` (or `python3 verify_live.py
  tv-<build>`) and its exit code."
- **Missing negative-test note** — "Acceptance (runnable) does not show
  the regression guard catches the bug it names. Add a sentence naming
  the simulated broken state and which test fails on it."

Out of scope: changing what "done" means for methodology, copy, or publish
(still the human's gate). A passing check proves the section is shaped
right; it does not approve publishing.

## Claude Code Handoff Template

```text
Repo: fantasy-tools
Branch/status: <branch, important uncommitted files, latest relevant commit>

Task:
<one concrete question or investigation>

Context:
- <files/docs to read first>
- <project rules that matter, especially fail-closed data rules>
- <known commands, failures, or observations>

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
