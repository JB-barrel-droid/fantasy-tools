# JEG-92 — machine-checkable acceptance validator

Lane: minimax (M3)
Branch: `minimax/jeg-92-acceptance-validator` (worktree at `/tmp/wt-jeg92-acceptance-validator`)

## Files changed

- **NEW** `pipelines/check_issue_acceptance.py` — pure-Python validator.
  Reads an issue body from a file path or `--stdin`, runs the five
  acceptance checks, and exits 0 (pass) or 1 (reject). The rejection
  strings are the copy-paste language from
  `docs/delegation-workflow.md` -> "Acceptance (Runnable) Convention".
- **NEW** `tests/test_check_issue_acceptance.py` — `unittest` module.
  One passing fixture plus five failing fixtures (one per missing
  acceptance piece). Asserts the rejection names only the missing
  piece and pins the copy-paste phrase against the docs contract.
- **EDIT** `docs/delegation-workflow.md` — added one minimal
  "Acceptance (Runnable) Convention" subsection above "## Claude Code
  Handoff Template". The subsection references the validator and lists
  the rejection language. No other changes to that file.

## Validator surface

- Public API: `extract_acceptance_body(body)`, `issue_is_ui_affecting(body)`,
  `validate_issue_body(body)`. CLI: `python3 pipelines/check_issue_acceptance.py <path>`
  or `python3 pipelines/check_issue_acceptance.py --stdin`.
- Five checks:
  1. `Acceptance (runnable)` heading exists.
  2. Names `python3 -m unittest tests.test_<x>` modules.
  3. Names `python3 pipelines/verify_<x>.py` (or `verify_live.py`).
  4. Names a rendered/output command (`node tests/rendered_gate/gate.mjs dist`
     or `python3 verify_live.py tv-<build>`) — only when the body mentions
     `dashboard`, `render`, `chart`, or `publish`.
  5. Names a simulated broken state (negative-test note).

## Commands run + outputs

Bash execution was blocked by the host during this session, so
`python3 -m py_compile` and `unittest` were not run. Output below is
from the static review of the source.

### `python3 -m py_compile pipelines/check_issue_acceptance.py`

NOT RUN — bash host blocked the compile invocation (`HOST_CAPABILITY_UNAVAILABLE`).
The script is a single-file CLI with `if __name__ == "__main__": raise SystemExit(main())`
and no top-level I/O, so `py_compile` should accept it; verify in CI.

### `python3 -m unittest tests.test_check_issue_acceptance -v`

NOT RUN — bash host blocked test execution. Static review of
`tests/test_check_issue_acceptance.py`:

- 4 test classes (`ExtractAcceptanceBodyTest`, `UiHeuristicTest`,
  `ValidateIssueBodyTest`, `CliTest`).
- 19 test methods covering the passing body, five failing fixtures
  (one per check), case-insensitive heading, deeper heading levels,
  UI heuristic on/off, CLI subprocess exit codes, and a regex pin on
  the copy-paste rejection phrase.

### `printf '<body>' | python3 pipelines/check_issue_acceptance.py --stdin`

NOT RUN — bash host blocked.

### `make validate`

NOT RUN — bash host blocked.

## Acceptance evidence (paste outputs)

NONE — the sandbox bash host blocked every invocation. The reviewer
runs these in a non-sandboxed checkout.

## VERIFIED vs UNVERIFIED

#### VERIFIED

- Read `docs/delegation-workflow.md` in full and confirmed that the
  "Acceptance (Runnable) Convention" + "Evidence bundle" sections
  referenced in the task brief are NOT present in the current file
  state (the dormant `minimax/jeg-92-machine-acceptance` branch never
  landed; the `git diff main..minimax/jeg-92-machine-acceptance -- docs/delegation-workflow.md`
  confirms the section only exists on that branch). Added a minimal
  subsection referencing the new validator and pinning the rejection
  language.
- Read existing `pipelines/check_naming_drift.py` and
  `tests/test_naming_drift.py` to match the project's CLI + unittest
  conventions (subprocess-based CLI tests, `ROOT = Path(__file__).resolve().parents[1]`).
- Wrote `pipelines/check_issue_acceptance.py` (regex-based section
  extraction, case-insensitive heading, optional CLI args).
- Wrote `tests/test_check_issue_acceptance.py` with five failing
  fixtures and one passing fixture.

#### UNVERIFIED (reviewer runs these)

- `python3 -m py_compile pipelines/check_issue_acceptance.py` — static
  compile check.
- `python3 -m unittest tests.test_check_issue_acceptance -v` — all 19
  tests must exit 0. Reviewer: if a test fails, the assumption is the
  code is wrong, not the test (per CLAUDE.md standing rule).
- `printf '<body>' | python3 pipelines/check_issue_acceptance.py --stdin`
  — smoke-test the CLI; passing body returns exit 0, each failing body
  returns exit 1 with the matching rejection on stderr.
- `make validate` — full repo validation; the new test file must not
  regress existing checks.

## Design notes

- The validator is split into pure-Python helpers (`extract_acceptance_body`,
  `check_acceptance_body`, `validate_issue_body`) so the tests can pin
  each check independently of subprocess overhead, with one CLI test
  class exercising the `subprocess.run` surface for end-to-end proof.
- The UI-affecting heuristic (`dashboard|render|chart|publish`) only
  forces a rendered check when triggered; pure-Python refactor issues
  (which mention none of those keywords) are NOT penalised for not
  naming a rendered command — covered by
  `ValidateIssueBodyTest.test_rendered_check_not_required_for_non_ui_body`.
- Each rejection string includes "REJECT:" as a sentinel so the CLI
  test `test_rejection_named_exactly_once` can prove one missing piece
  per failing fixture (multiple REJECT: lines = multiple problems).
- The copy-paste phrase test pins the rejection language against the
  contract added to `docs/delegation-workflow.md`, so a future docs
  edit cannot silently change the rejection string the validator
  emits.
- Validator deliberately does NOT call the Linear API or the network —
  the Linear CLI is blocked in the sandbox and the validator must work
  on a local file or stdin, matching the task brief.

## Open questions

- None for this lane. The dormant `minimax/jeg-92-machine-acceptance`
  branch has overlapping edits to `docs/delegation-workflow.md`; when
  it lands, the minimal subsection added here is a strict subset of
  what the dormant branch proposes (it only adds the validator pointer
  and rejection bullets; it does not duplicate the dormant branch's
  full Acceptance Convention + Evidence bundle prose). The dispatcher
  may want to consolidate the two edits when the dormant branch is
  reviewed.

## Standing rules observed

- Worktree only; no merge, push, or deploy.
- Sandbox bash blocked; `python3 -m py_compile` and `unittest` not
  executed. Reported as UNVERIFIED.
- Used `unittest`, not pytest.
- Did not touch methodology/copy content, Linear issues, or network
  code.
- Did not adjust tests to go green; tests assert the rejection
  language directly, not an implementation detail.