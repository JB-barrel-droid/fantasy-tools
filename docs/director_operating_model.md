# Director Operating Model

This repo does not use a separate delegated-agent runtime today. The operating
model is a simple handoff discipline for any AI or human session working in the
repo.

## Stores Of Record

- `execution/current-plan.md` is the only live plan.
- `docs/risk-register.md` is the durable gap/risk/follow-up register.
- `docs/claude-log/` is the session evidence log (one file per PR/session;
  `docs/claude-log/README.md` has the format; `docs/claude-log.md` is the
  frozen pre-2026-10-07 archive).
- `README.md`, `SYSTEM_MAP.md`, `docs/methodology.md`,
  `docs/modular-pipeline.md`, and `docs/pipeline-rules.md` are the standing
  operator and methodology docs.

Do not create alternate backlog, status, gap, or run-history files.

## Session Rules

1. Read the required context docs before editing.
2. Inspect relevant implementation files before changing them.
3. Make the smallest reversible change that closes the named gap.
4. Run the minimum relevant validation.
5. Record outcomes:
   - session evidence in `docs/claude-log/YYYY-MM-DD-<slug>.md`;
   - durable unresolved or fixed gaps in `docs/risk-register.md`;
   - live next steps only in `execution/current-plan.md`.

## Gap Rule

A gap is not considered recorded if it exists only in chat. Any durable issue
must have an entry in `docs/risk-register.md` with status, evidence, and next
action.
