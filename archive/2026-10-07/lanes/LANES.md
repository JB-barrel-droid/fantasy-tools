# Lane Outbox/Inbox Protocol (draft v0 — JEG-94)

File-based task channel between Roman (`owner:muse`) and the Claude / ChatGPT
lanes. Linear comments are the wake-up signal; the brief files are the work
orders. Supplements `docs/delegation-workflow.md` (handoff templates, owner
labels); it does not replace it.

## Layout

```
lanes/
  outbox/<lane>/<JEG-nn>-brief.md    # Roman -> lane (the work order)
  inbox/<lane>/<JEG-nn>-result.md    # lane -> Roman (the result)
  LANES.md                            # this file
```

`<lane>` is `claude` or `chatgpt`.

## Posting a brief (Roman)

1. Write `lanes/outbox/<lane>/<JEG-nn>-brief.md` following the brief format below.
2. Post a comment on the Linear issue: `Brief ready: lanes/outbox/<lane>/<JEG-nn>-brief.md`.
3. The lane picks it up from its next session (or immediately via `codex exec`
   once the CLI connector is live).

## Brief format

```text
Issue: JEG-nn — <title>
Lane: <claude|chatgpt>
Branch: <issue branch name>

Task:
<one concrete task, one lane, one module>

Context:
- <files/docs to read first>
- <project rules that matter — name the standing rules, don't assume they're known>
- <known failures or observations>

Acceptance (runnable):
- <exact test files / verify commands that prove done>

File boundaries:
- May touch: <paths>
- Must not touch: <methodology, values, copy, publish surfaces — be explicit>

Result contract:
- Write lanes/inbox/<lane>/<JEG-nn>-result.md with: files changed, commands run
  + results, acceptance evidence (paste the outputs), open questions.
- Comment on the Linear issue when the result lands.
- Never merge, push, or deploy. Never claim done without the evidence bundle.
```

## Claiming a brief (lane)

1. Read the brief and the linked Linear issue (status, comments).
2. Do the work inside the file boundaries.
3. Run the runnable acceptance checks; paste outputs into the result file.
4. Write `lanes/inbox/<lane>/<JEG-nn>-result.md` and comment on the issue.
5. If the brief conflicts with a standing rule in `docs/` or `AGENTS.md`, stop
   and say so in the result file — the doc wins, not the brief.

## Lane rules (standing)

- One active brief per lane per module. Finish or hand back before taking another.
- Done = evidence bundle attached. No bundle, no done.
- Lanes never merge, push, deploy, or touch `main`.
- Roman integrates every result per the Integration Checklist in
  `docs/delegation-workflow.md` before it ships.

## Minimax subtask pattern (standing 2026-10-02, Jeremy)

The minimax lane dispatches SUBTASKS, not whole issues (see
`ROUTING.md` "Dispatch pattern"). Muse decomposes the issue first; each
minimax brief follows the format above with one concrete subtask, file-level
boundaries, and runnable acceptance. Whole-issue briefs go to minimax only
when the issue is already subtask-sized.

## Direct tasking: wire protocol (JEG-94)

File-based briefs above carry the work order; this section documents the
machine-readable wire protocol for direct inter-lane tasking, implemented
in `lanes/protocol.py` and driven via `bin/mmcode`.

### Brief (JSON)

A brief is a JSON object a dispatcher writes into `lanes/outbox/<dest_lane>/`:

| field        | required | meaning                                                                 |
| ------------ | -------- | ----------------------------------------------------------------------- |
| `issue`      | yes      | Linear issue key, e.g. `JEG-94`. Pattern `^[A-Z][A-Z0-9]{0,15}-[0-9]{1,6}$`. |
| `lane`       | yes      | Destination lane (must be in `KNOWN_LANES`, today just `minimax`).      |
| `from`       | yes      | Origin lane (must be in `KNOWN_LANES`).                                 |
| `subject`    | yes      | One-line summary. Non-empty.                                            |
| `context`    | yes      | Long-form text. Non-empty.                                              |
| `created_at` | yes      | ISO-8601 UTC, e.g. `2026-10-02T20:15:00Z`. Set at write time.           |
| `signature`  | yes      | `sign(lane, issue, created_at)` = `<lane>|<issue>|<ts>`.                |

Build with `lanes.protocol.make_brief(...)`, write with
`lanes.protocol.write_brief(...)` (re-validates, refuses duplicates —
the outbox is append-only).

### Result (JSON)

A result is a JSON object the worker writes into `lanes/inbox/<worker_lane>/`:

| field        | required | meaning                                                                |
| ------------ | -------- | ---------------------------------------------------------------------- |
| `issue`      | yes      | The brief's issue key.                                                 |
| `lane`       | yes      | The WORKER lane (who produced this). Must equal the brief's `lane`.    |
| `result_of`  | yes      | Echo of `issue` — a result cannot claim to answer a different issue.   |
| `subject`    | yes      | One-line summary of what was produced.                                 |
| `context`    | yes      | Long-form text: the work, the evidence, the open questions.            |
| `created_at` | yes      | ISO-8601 UTC at the moment the worker signed.                          |
| `signature`  | yes      | `sign(lane, issue, created_at)` from the result's OWN fields.          |

The signature proves the result is internally consistent (nothing tampered
after signing); it is NOT tied to the brief's timestamp — a worker can only
sign its own moment. Build with `make_result(...)`, write with
`write_result(...)`.

### Reviewer verification

The reviewer runs:

```bash
python3 -m lanes.protocol verify \
    --brief  lanes/outbox/<lane>/<issue>-<epoch>.json \
    --result lanes/inbox/<lane>/<issue>-<epoch>.json
```

`verify_signature(result, brief)` enforces, in order:

1. The result is well-formed, including a signature that recomputes from
   the result's own `(lane, issue, created_at)`.
2. The brief is well-formed.
3. `result["lane"] == brief["lane"]` (the worker really is who was asked).
4. `result["issue"] == brief["issue"]`.
5. `result["result_of"] == brief["issue"]`.

Any failure exits 1 and prints `FAIL: <reason>` — there is no override flag.
An unverifiable result is treated as if it did not arrive.

### Adapter interface

Every per-lane connector implements `lanes.protocol.LaneAdapter`:

```python
class LaneAdapter(ABC):
    name: str
    def dispatch(self, brief, *, dry_run=False) -> Dict[str, Any]: ...
    def self_test(self) -> Tuple[bool, str]: ...
```

`dispatch` must re-validate the brief, refuse a brief addressed to another
lane, build the result via `make_result`, and write it via `write_result`
unless `dry_run=True`. Dry-run is the default for every test/automation
path: the adapter must not touch the inbox or any external system.

Today the shipped adapters are `MiniMaxAdapter` and the ChatGPT API adapter
(`lanes/chatgpt_adapter.py`, shipped 2026-10-04). The chatgpt adapter dispatches
outbox markdown briefs to the OpenAI API via the `custom.openai` credential and
writes results to `lanes/inbox/chatgpt/` — it is the lane for review/analysis
briefs and bounded text work. (`codex exec` remains broken on this host for
agentic repo work; the API path does not need the codex tool host.) Shipping a
new lane adapter means
subclassing `LaneAdapter`, registering a CLI under `bin/<lane>`, and
extending `KNOWN_LANES` — never extend `KNOWN_LANES` without an adapter.

### CLI: `bin/mmcode`

Thin wrapper around `python3 -m lanes.protocol`:

| subcommand          | purpose                                              |
| ------------------- | ---------------------------------------------------- |
| `make-brief`        | Build + sign + write a brief to `lanes/outbox/<lane>/` |
| `make-result`       | Build + sign + write a result to `lanes/inbox/<lane>/` |
| `dispatch`          | Build a brief and run it through the adapter         |
| `verify`            | Reviewer gate: verify a result against its brief      |
| `adapter-self-test` | Round-trip the shipped adapter in dry-run mode       |

### Tests

`tests/test_lane_protocol.py` covers: signature pass on a well-formed
pair; fail-closed on missing signature, wrong lane, wrong issue, wrong
`result_of`, tampered signature, tampered `created_at`; adapter dry-run
returns the would-be result without writing; live dispatch writes one
signed result; malformed brief rejected (unknown lane, bad issue key,
naive timestamp); CLI `verify` exits 0 on success / 1 on failure.
Wired into `make test-unit`.

### Open follow-ups (not in this ticket)

- HMAC over the brief body once a secrets layer is approved (Phase 2).
- Auto-poll-and-pick-up loop (`mmcode watch`) — today a dispatcher and a
  worker talk by hand or by a cron.
