# Prompt for ChatGPT — fantasy-tools issue batch (paste as-is)

You are working in the repo `JB-barrel-droid/fantasy-tools` (GitHub Pages site:
https://jb-barrel-droid.github.io/fantasy-tools/). Roman (the PM agent) has
assigned you three Linear issues, labeled `owner:chatgpt` in the "Jegabee" team:

1. **JEG-17** — Full rendered production QA pass of the trade value chart
2. **JEG-29** — Rebuild the local guard harness: run curve-widget guard math
   against fixture data (the old harness files are unrecoverable — rebuild
   from scratch against the current guard math in
   `app/trade-value-chart/assets/curve-widget.js`)
3. **JEG-45** — Fix the QA-003 lock-revert notice: it is added and removed in
   the same synchronous block, so it never paints

Read each issue in Linear for problem, background, in/out of scope, and
acceptance criteria before starting.

## Standing rules (non-negotiable)

- Work on issue branches named `chatgpt/<issue>` (e.g. `chatgpt/jeg-29-guard-harness`).
  Branch from current `origin/main`.
- Open **draft PRs**. Never merge, never push to `main`, never deploy.
  Roman reviews every PR for methodology regressions, merges in lane order,
  validates, deploys, and runs final production verification.
- Keep each branch scoped to its issue. One issue per branch.
- The pipeline is free-only sources. Freshness = content vintage, never pull time.
- Never publish on a known flaw; never display unvalidated values.
- Names resolve through the canonical naming table; ambiguous identities are
  excluded fail-closed, never guessed.
- Read `docs/delegation-workflow.md` (your lane + the integration checklist),
  `docs/pipeline-rules.md`, and `~/workspace/fantasy-tools/AGENTS.md` before
  writing code.

## Regression-guard rule (applies to JEG-29 especially)

Every regression guard must prove it catches the bug it names: test it against
a simulated broken state. A guard that asserts current behavior as correct
without checking which state is right is worse than no guard. Derive guards
from registries, never hardcode counts.

## Validation

- Run `make validate` (the repo's default validation gate) before opening each PR.
- `dist/` is generated — never edit it as source.
- Report: branch, commits, files changed, commands run and results, what you
  verified, and what remains unverified (say "unverified" explicitly where
  you could not check).

## Coordination notes

- JEG-17's QA pass runs after Roman's next deploy, not before — check with
  Roman on timing.
- JEG-22's diagnosis was corrected (merged PR #11): the bench-share caption
  is a labeling question, not staleness. Read that correction before touching
  anything near the curve caption.
- Claude Code owns a separate batch (JEG-23/JEG-44, JEG-21/22/24, JEG-8) —
  do not take those.
- Suggested order: JEG-45 (small, well-scoped), then JEG-29, then JEG-17.
