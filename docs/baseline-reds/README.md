# Known baseline reds (JEG-1450)

Reviewers and agents must check this registry before calling a red a regression.

`registry.json` records exact unittest IDs, observed failure environments,
first recorded main reproduction SHA, owning ticket and reason. Match both ID
and environment: a local red does not excuse a CI failure. This is attribution,
never an allowlist: the wrapper preserves the gate's exit status. Remove an
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
Skipped, absent, red or missed nights break the streak. Manual runs on main
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

The reviewer rule above will also be added to AGENTS.md after PR #1250 merges;
this PR intentionally leaves that file untouched.
