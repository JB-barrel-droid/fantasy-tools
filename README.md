# Fantasy Tools Migration

This repository is the migration target for the fantasy-football Trade Value Dashboard currently running in Muse.

Current status: discovery has started from the migration handoff PDF. The Muse ZIP/code/data export has not yet been present in this workspace, so source-file inspection and local dashboard reproduction are pending that artifact.

## Goals

- Preserve the current Muse dashboard as the reference implementation.
- Reproduce the current Trade Value Dashboard outside Muse using the existing finished data artifacts first.
- Keep Supabase as the production database.
- Move calculations and collectors out of Muse incrementally only after equivalence tests exist.

## Intended Structure

- `app/` - lightweight web dashboard outside Muse.
- `trade_value/` - Trade Value domain logic and adapters.
- `pipelines/` - reproducible build and data-artifact generation steps.
- `shared/` - shared identity, scoring, team, and Supabase access helpers.
- `tests/` - regression and golden-output tests.
- `docs/` - migration documentation and status.

The exact source layout may be adjusted after the Muse ZIP is inspected. Existing paths should be preserved initially if that makes behavioral verification easier.

## Local Run

Pending the Muse export. The minimum viable local target is expected to be:

```bash
python3 -m http.server 8000 --directory app/trade-value-chart
```

Then open:

```text
http://localhost:8000
```

## Tests

Pending the Muse export. The first regression suite should cover static dashboard behavior and JSON fixtures before any business logic is moved:

```bash
python3 -m pytest
```

## Git Note

This workspace currently rejects creating `.git`. A persistent external Git directory is being used at `.gitstore/` until normal repository metadata can be created.

Use:

```bash
git --git-dir=.gitstore --work-tree=. status
```

## Secrets

Do not commit `.env`, Supabase keys, service-role keys, cookies, browser sessions, FantasyPros credentials, or any raw private export containing secrets.
