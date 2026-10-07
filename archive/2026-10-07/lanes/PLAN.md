# Operating-Model Plan Tracker (JEG-96)

This directory holds the machine-readable pieces that make the operating
model run without Jeremy's policing.

## Files

- `plan.json` — phase definitions, ticket lists, entry/exit criteria,
  merge-charter tier definitions, merge queue spec. Hand-maintained;
  describes structure.
- `linear_fixture.json` — current Linear ticket statuses (Done, Backlog,
  etc.). **State is derived from this file at read time, not from
  `plan.json`.** Replace via the refresh procedure below.
- `merge_charter.py` — encodes the tier rules and merge queue as checkable
  Python. CLI: `python3 lanes/merge_charter.py docs/PLAN.md`.
- `plan_status.py` — CLI: prints which phase is active, what's blocking
  it, what's next. `make plan-status` runs it.
- `test_plan_tracker.py` — discrimination tests for both the tracker and
  the charter. Wired into `make test-unit`.

## Refresh procedure (manual — Linear CLI is not in this sandbox)

The Linear CLI is not reachable from this sandbox, so the fixture is
refreshed by hand. On a machine with the API token (any lane can do this):

1. Pull the current state of every ticket id in `plan.json` from Linear.
2. Build a `tickets: {id: {status: ..., title: ..., owner: ..., note: ...}}`
   map. Use lowercase status values: `Backlog`, `Todo`, `In Progress`,
   `In Review`, `Done`, `Cancelled`. The tracker treats `Done` and
   `Verified` (and `Cancelled`) as "complete enough" for phase exit.
3. Write the map to `lanes/linear_fixture.json` and bump
   `_last_refreshed`.
4. Commit the new fixture on the same lane branch as any other plan
   change. The PR's diff alone is the signal that the plan state changed.

For a one-shot script on a machine with `linear-cli`, this works:

```bash
linear issue list --team JEGABEE --ids JEG-77,JEG-78,JEG-79,JEG-80,JEG-81,JEG-82,JEG-83,JEG-84,JEG-91,JEG-92,JEG-93,JEG-94,JEG-95,JEG-96,JEG-71,JEG-55 \
  --json status,title,assignee.label \
  | python3 -c "import json,sys; ... # rewrite to lanes/linear_fixture.json"
```

## Adding or removing tickets

`plan.json` is the source of truth for which tickets belong to which phase.
If a new ticket joins a phase, add its id to the phase's `ticket_ids`
array; if it leaves, remove it. The fixture follows automatically
because the tracker looks up tickets by id, not by name.

JEG-95 must **not** be added — it is Cancelled/Superseded by JEG-96 and
including it would inflate Done counts.

## Boundary (always with Jeremy)

- values calls
- methodology changes
- user-facing copy
- destructive production actions
- outward-facing changes (except routine data refreshes through the
  pipeline)
- Tier 2 merge taps

Hands-off: routine data refreshes that follow the same methodology and
run fresh data through the pipeline to the published chart.

## Out of scope today (Muse-only lane)

- `claude` lane adapter — Codex CLI never verified working; not reachable
  from Muse.
- `chatgpt` lane adapter — codex account out of usage; not reachable from
  Muse.
- Full API-key lane identity machinery — cheap signed-result-files only;
  graduate to API keys only if the cheap version is ever gamed.

If a future session wants to re-enable either lane, the adapter belongs in
this same `lanes/` directory under a documented name (e.g.
`lanes/claude_adapter.py`) so the tracker can enumerate active lanes
without code reading.