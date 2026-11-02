# Known baseline reds (JEG-1450)

Reviewers and agents must check this registry before calling a red a regression.

`registry.json` records exact unittest IDs, observed failure environments,
first recorded main reproduction SHA, owning ticket and reason. Match both ID
and environment: a local red does not excuse a CI failure. This is attribution,
never an allowlist: the wrapper preserves a failing gate's exit status and a
valid registry leaves a passing status unchanged. A malformed registry still
runs the gate and streams its output, then returns 2 if the gate passed. Remove an
entry only after its owning ticket closes; three greens are a suggestion, not
automatic deletion. Confirm the ticket state in Linear during review.

Run a local gate with:

```sh
python3 -m pipelines.baseline_reds --context local -- make validate
```

Preview and Pages validation jobs, the nightly full suite and daily render
sweep print labels in their check logs and GitHub job summaries. The wrapper
enables verbose unittest output in child Python processes; existing test
execution and assertions stay intact. Non-unittest failures remain gate
failures and require reading their original output.

The main-branch nightly job persists per-test results in an Actions cache.
Only explicit `ok` results on three consecutive UTC dates produce `can remove`.
Skipped, absent, red or missed nights break the streak. History is separated
by context and only contexts listed in the entry can count; the local-only
JEG-1394 seed cannot earn a removal hint from CI/nightly passes. Manual runs on main
can supply that night's observation; reruns overwrite that date. Cache expiry
starts a fresh streak. No model, Linear credential or ticket mutation is used.
For another runner use `--history PATH --night YYYY-MM-DD` with nightly context.

Seed evidence checked 2026-10-31: JEG-1394 remains In Progress; its comments
record main reproduction at 7358589c and fix PR #1240. CI scope is deliberately
unseeded: recent #1240 checks (run 41149778909) skipped the draft's heavy jobs.
The saved-team keyboard/mobile `''` versus `'beta'` failure is recorded on
JEG-1394 and JEG-1450, but no open dedicated owning ticket was found in Linear's
finder search. It is not seeded pending confirmed ownership and a main SHA.
GitHub REST run-history lookup was rate-limited; GraphQL check receipts were
available. Do not broaden a seed's environments on that evidence.

The reviewer rule is also recorded in AGENTS.md.

Optional `signature` is a substring of that test's own failure traceback
(exception type or message); every captured failure for the ID must match.
JEG-1394 uses the null-property/value-setting error from the recorded slider
failure. Optional `expires` is an ISO date; entries remain valid on that date
and become new reds labelled `expired registry entry` after it. Registry loading
requires a non-empty test ID, SHA and reason, a `JEG-<digits>` ticket, and a
non-empty list of supported contexts.

A nonzero gate always reports whether failure attribution is complete.
`run_suite: failed:` commands without complete known unittest failure evidence
are listed as `unattributed failure`. Enclosing shell/make failures remain
unattributed even when their unittest failures are known. Only a direct plain
unittest invocation with complete matching failure counts can claim all
failures are known. Other commands, including pytest and node, require reading
the original output.

Seed additions (2026-11-02): JEG-1403 comments identify the three journey
methods at main c267aa71. JEG-1424's Mac report records test_tables market-sort
failures with main 951f95df integrated; the signature limits that attribution
to the opportunities failure. HANDOFF's Oct 30 JEG-1176 report at 168aba93
records missing chromium_headless_shell-1208 during week-history setup.
JEG-1450 owns that environment attribution row pending a dedicated environment
ticket. All are local-only observations; none excuse CI or nightly reds.
