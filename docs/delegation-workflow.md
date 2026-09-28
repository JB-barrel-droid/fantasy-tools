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
