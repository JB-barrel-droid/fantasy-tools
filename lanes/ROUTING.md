# Lane Routing & Capability Guard (draft v0 — JEG-94 / JEG-97)

Not every task may go to every lane. This file is the routing table the
autonomous sweep reads before dispatching. A task is dispatched to a lane
only if every capability it requires is in that lane's column.

## Capability matrix

| Task class | Examples | minimax (mcode) | claude | chatgpt | muse (Roman) | jeremy |
|---|---|---|---|---|---|---|
| repo code change | pipeline Python/JS, tests, guards, monitor checks, docs | YES | YES | YES | YES | — |
| wiring verification | run verify scripts, check fixtures/bytes | YES | YES | YES | YES | — |
| needs vision / OCR | read text from screenshots/images | NO | MAYBE | MAYBE | YES | — |
| needs live browser | rendered-page checks, screenshots, console | NO | NO | NO | YES | — |
| needs credentials | Supabase DDL via SQL editor, OAuth flows | NO | NO | NO | YES | — |
| needs Mac-only files | Razzball snapshot on Jeremy's machine | NO | NO | NO | relay | YES |
| methodology decision | indexation, VORP math, pricing logic changes | NO | advise | advise | advise | YES |
| values / copy calls | what the chart shows, user-facing words | NO | NO | NO | NO | YES |
| cross-model review | review of another lane's PR | NO (own work) | — (unavailable) | — (unavailable) | YES | — |
| merge / push / deploy | anything touching main | NO | NO | NO | YES (per charter) | Tier 2 |

"advise" = may write options + recommendation; Jeremy decides.
"relay" = Roman prepares everything; Jeremy runs the step on his machine.

## Lane availability (standing directive 2026-10-02, Jeremy)

- **claude lane: UNAVAILABLE from Muse.** "Stop trying to use the claude CLI.
  So far we only have evidence we can run minimax out of muse." The claude
  CLI was never verified working from Muse (auth hit Anthropic's
  token-endpoint rate limit and never recovered). Do not design around it as
  an active lane.
- **chatgpt/codex lane: AVAILABLE (verified 2026-10-03 ~14:05 CDT).** Jeremy
  corrected the mechanism to ChatGPT subscription OAuth (not metered API
  billing); device-auth completed, `codex login status` = "Logged in using
  ChatGPT", and a `codex exec` smoke probe returned OK. M3 stays the default
  FIRST option (standing directive); codex is a valid second/parallel lane
  for repo code changes and wiring verification per the capability table.
  Dispatch still needs `lanes/protocol.py::KNOWN_LANES` to list it (currently
  `("minimax",)` only) — re-enabling dispatch is a deliberate dispatcher
  change, not automatic.
- **Effective routing:** minimax (M3) for everything it can physically do
  (per the capability guard); muse (Roman) for the rest. Escalation on two
  failures goes to muse, never to an unavailable lane.

## Difficulty routing (within the code-change class)

**Standing directive 2026-10-02 (Jeremy): minimax is the FIRST option for everything
it can physically do, because it is cheap. Dispatch as subtasks (see Dispatch
pattern below); escalate a subtask to muse (Roman) after two failed attempts.**

| Difficulty | Signal | Route to |
|---|---|---|
| routine | well-scoped ticket, runnable acceptance, repo-local, no design judgment | minimax first (proven) |
| thinking | architecture judgment, multi-subsystem debugging, methodology analysis, competing hypotheses | minimax FIRST; escalate to muse on 2 failures |
| frontier | advanced logic/math only | minimax FIRST as a probe; muse on 2 failures (claude/chatgpt lanes unavailable) |

The old "route by difficulty" table is retired. The capability guard above still
stands (minimax never gets what it cannot physically do). Everything else goes to
minimax first; the two-failure rule is the escalation mechanism, not a pre-judgment.

### Model selection (standing directive 2026-10-02, Jeremy: "use M3 for everything and stop with the M2.5")

M3 (`custom_provider:minimax-coding-plan/MiniMax-M3`) is the ONLY model for
minimax dispatches. No M2.5 carve-out remains — earlier the policy allowed M2.5
for mechanical L1/L2 work, but Jeremy retired that on 2026-10-02 after the
JEG-103 head-to-head (M3 won decisively on fix placement and test quality) and
the JEG-92 design probe (M3 markedly more honest in reporting). Every dispatch
uses `--model custom_provider:minimax-coding-plan/MiniMax-M3`.

Evidence: JEG-103 L3 head-to-head — M3 chose the correct central-setter
architecture and tested rendered behavior; M2.5 missed a mutation path and
tested an internal variable. JEG-92 L4 — M3 produced a strong acceptance
convention with honest verified-vs-unverified split. M2.5 remains fine for
mechanical work (JEG-90 L1 defect fix, JEG-100 L2 repair, JEG-99 rounds 2–3,
JEG-75 round 2) but its test claims need the same independent verification as
M3's, and its "tests pass" assertions have been wrong on invented names twice
(JEG-92 r2 rewrote every test name; JEG-99 r3 wrote 2 tests contradicting the
spec).

## Dispatch pattern (standing directive 2026-10-02, Jeremy)

Muse decomposes; M3 executes; Muse reviews and integrates.

Rationale: M3's failures cluster at scoping/design, not execution. JEG-101
attempt 1 produced 65KB of thinking and zero files (analysis paralysis on a
multi-constraint task); JEG-87 fabricated "evidence" to satisfy a validation
contract; JEG-92 invented every test name. Its bounded execution is strong:
JEG-86/87/98/101 all landed REVIEWED-READY as tight single-file tasks. So the
dispatch unit is the SUBTASK, not the issue:

1. Muse breaks the issue into subtasks. Each subtask brief carries: file-level
   scope (may-touch / must-not-touch), runnable acceptance (exact commands),
   the standing rules that apply, and the result contract (code+tests, never
   claim test results — verification happens outside the sandbox by the reviewer).
2. M3 executes subtasks in parallel, one worktree+branch per subtask. No two
   workers on the same files.
3. Muse reviews each result independently, repairs what the worker got wrong,
   runs the acceptance commands, and integrates. A subtask that fails review
   twice goes to muse (Roman) — never a third blind retry.

Whole-issue dispatch only when the issue is already subtask-sized (single file
or single concern, e.g. the JEG-85/86/87 week-coding pullers).

## Sophistication ladder (retired 2026-10-02 — log kept as history)

The ceiling-probing experiment is over: we operate below M3's ceiling via the
dispatch pattern above instead of finding where results go bad. The log stays
as the evidence base for the pattern.

- L1: single-file additive scripts + unit tests
- L2: repair own bugs against precise review feedback
- L3: multi-file changes touching existing logic
- L4: feature work with design judgment inside guardrails
- L5: novel debugging, cross-subsystem, methodology-adjacent (never methodology decisions)

### Ladder log (date, ticket, level, outcome)

- 2026-10-02: JEG-76/99/100 round 1 (L1) — all three NEEDS WORK on review (unrun tests, wrong fixture paths, SyntaxError, spec mismatches). Round 2 (L2) dispatched: can it repair against precise feedback?
- 2026-10-02: JEG-103 (L2/L3: JS readout fix + rendered regression guard) dispatched fresh.
- 2026-10-02: JEG-75 round 1 (L3: 10-file normalizer centralization) — NEEDS WORK. Worse than mechanical: the swap introduced behavior deltas (5/13 tricky names) and broke 3 fail-closed identity tests — the NICKNAMES mapping guesses, violating the standing \"nothing is guessed\" rule. Judgment error on a standing rule, not just a bug. Round 2 (L2) dispatched with revert+audIt instructions.
- 2026-10-02: MODEL A/B (Jeremy: try both, usage is cheap, really push it) — JEG-103 head-to-head: M2.5 (default) vs M3 on separate branches, independent review of both. JEG-92 (L4 design-heavy: machine-checkable acceptance) -> M3 as the harder probe. JEG-90 migration defect -> M2.5. 8 workers total in flight.
- 2026-10-02: STRUCTURAL FINDING — the mmcode exec sandbox blocks test execution AND the linear CLI (3 workers now: JEG-99 r2, JEG-103 M2.5 both reported "permission gates"). Workers ship unverified claims. New pipeline: workers write code+tests and must NOT claim test results; verification (run tests, post Linear comments) happens outside the sandbox by Roman/reviewer. Prompts updated accordingly.
- 2026-10-02 JEG-90 (M2.5, L1 defect probe): worker found and fixed a REAL defect (migration 005 DROP INDEX on a unique constraint -> DROP CONSTRAINT + comment) and correctly refused DB writes. Same sandbox pattern: shipped a broken guard (pytest import, repo is unittest-only) and could not create the Linear issue. Repaired outside the sandbox: unittest-ified, discrimination proven (fails pre-fix, passes post-fix), wired into make test-unit, created JEG-104. READY on branch minimax/jeg-90-migration-constraint.
- 2026-10-02 JEG-100 r2 (M2.5, L2 repair): worker fixed the fixture-path bug and wrote 12 tests but shipped 2 broken ones; also the flip counts were nondeterministic across runs (tied pairs flipped on set order). Repaired outside sandbox: fixed tests, added explicit native+reindexed tie-skips -> deterministic 54,726 flips / 33 combos. READY on branch minimax/jeg-100-fidelity-ordering.
- 2026-10-02 JEG-99 r2 review (M2.5): mechanical items fixed and verified (4/4 tests pass), BUT codex polling still HTTP not app-server protocol — second failure on the same item + false compliance claim in docstring. Per two-attempt rule the protocol piece is DESCOPED by ticket comment (codex auth broken anyway: device-auth timed out, account out of usage). Round 3 dispatched as a NARROW mechanical repair: unknown lanes fail closed, depletion markers gate, claude reports unknown not 0%, short error strings. JEG-101 stays held.
- 2026-10-02 JEG-92 r1 (M3, L4 design probe): strong first design-heavy result. Convention doc is concrete and properly scoped (methodology/copy/publish explicitly out). All 11 named test modules + 5 scripts verified to exist. Report honesty markedly better than M2.5: explicit verified-vs-unverified split, exact file/line cross-checks, flagged an open gap (JEG-23) instead of inventing a test. ONE miss: the 5 pilot issues are all Done/closed, not currently-open as instructed (misread board state). Sent back as narrow L2 repair with the 5 explicit open issue IDs (JEG-75/76/99/100/103). Early signal: M3 materially better at judgment/honesty than M2.5 on L4 work.
- 2026-10-02 JEG-103 M3-vs-M2.5 verdict (L3): M3 WINS decisively. Fix placement: central setter (all paths incl. dblclick) vs M2.5 per-handler (missed dblclick). Test quality: M3 targeted the rendered defect; M2.5 tested an internal variable with a broken harness. Both shipped unrunnable tests (sandbox), but M3 was honest about it and its harness was repairable in ~10 iterations; M2.5's tested the wrong thing entirely. Repaired + discrimination-proven (2 fail pre-fix / 6 pass post-fix). READY on minimax/jeg-103-bench-readout-m3. Standing lesson reinforced: M3 for anything needing judgment; M2.5 fine for mechanical L1/L2 with tight specs.
- 2026-10-02 JEG-75 M2.5 round 2: REVIEWED-READY. All 5 blockers fixed: guard heuristic no longer false-positives, Razzball swap reverted (identity tests green), other swaps deliberately reverted not silently changed, guard in make test-unit, docs entry. Worker made the RIGHT conservative call reverting all semantic-changing swaps under the fail-closed rule. Standing lesson: when the canonical normalizer differs on 5/13 tricky names, migration is thinking-lane work, not mechanical swap work — M2.5 correctly refused to guess. Corrected one worker docs falsehood (claimed it created canonical_players.py, which pre-existed).
- 2026-10-02 JEG-99 M2.5 round 3: REVIEWED-READY after test repair. Worker fixed all 4 mechanical defects correctly; its 2 new tests contradicted the spec (expected 1% used with a depletion marker present; tested corrupt-JSON instead of the real exception path). Repaired both, 11/11 green. Standing lesson: worker tests assert the spec as WRITTEN in the ticket, not the code as built — when the two disagree, read the ticket, not the test.
- 2026-10-02 JEG-92 M3 round 2: REVIEWED-READY after name corrections. Worker did the right things (open-issue pilots, honest missing-file flags) but invented EVERY test/class name and one whole fixture contract - commands would fail even after files land. Rewrote with exact names verified against the real lane branches. Standing lesson: machine-checkable means copy-paste-runnable; a plausible-looking test path is worse than "not yet in repo" because it fails SILENTLY at acceptance time. Always verify names against the branch that owns the file.
- 2026-10-02 M3 DEFAULT + 5-way parallel dispatch (Jeremy: "blast through the backlog"). M3 made the default model (skill + routing + memory updated). Dispatched: JEG-101 (multi-account usage watcher, builds on jeg-99 branch), JEG-85/86/87 (CBS/FantasyPros/FantasyCalc week-coding, rerouted from dead chatgpt lane), JEG-98 (lineage top-25 for 4 adjusted legs, rerouted from dead chatgpt lane). Workers barred from docs/week-coding-rules.md (shared file; Roman updates status table at merge). Each on its own worktree+branch.
- 2026-10-02 JEG-87 REVIEWED: M3 worker output needed reviewer correction (3 defects: synthetic page-title evidence violating Rule 1, &week=N on never-fetched URL, tuple-unpack crash on string cache keys + wrong ppr map). Fixed in Roman lane (commit e3e1c77); 23/23 unittest green with discrimination proven against pre-fix code. Lesson: M3 will fabricate "evidence" to satisfy a validation contract — reviewers must check that validated inputs are genuinely independent of the request, not derived from it. READY posted to Linear.
- 2026-10-02 JEG-101 REVIEWED: M3 attempt 2 wrote real files (attempt 1 wrote only thinking-block analysis). Reviewer fixed 2 fail-open bugs: unknown-lane fall-through returning True, and uninjected codex accounts dispatching on _default_usage 100%-remaining. 14/14 tests green, discrimination proven. READY posted to Linear.
- 2026-10-02 JEG-85 REVIEWED: M3 worker structurally sound. Reviewer fixed 2 bugs: og:title regex truncated at apostrophe on the live page ("Dave Richard's ..." -> "Dave Richard", silently dropping week evidence), and the e2e test's fetch patch was a no-op (bound default arg) so tests hit the live network. 20/20 green, hermetic, discrimination proven. Lesson: regexes for attribute values must be quote-aware; a patch that doesn't change behavior is a test that proves nothing — check the suite actually runs hermetic. READY posted to Linear.
- 2026-10-02 JEG-98 REVIEWED: M3 worker solid. Reviewer fixed: test fixture missing 2 of 4 legs + wrong combo key (half_12 vs half_12_qb1); adjusted tables had identical labels to parents (now 'X (adjusted)'); chart ✗ red-by-design now titled. 19/19 green; builder smoke-tested on real fixture (coherent chains, e.g. Gibbs 75.1→70.0→×1.0286→72.0). Lesson: fixtures must mirror real combo keys per source; identical headings for distinct tables is a defect, not label reuse. READY posted to Linear.
- 2026-10-02 JEG-105 DONE (Jeremy picked B): adjusted-leg chart_matches_indexed now checks the leg's own adjusted value (green by construction, same shallowness as parents); dead tooltip branch removed; 19/19 green + real-fixture smoke test. JEG-106 filed for the parent-leg false-green (needs his (a)/(b)/(c) pick).
- 2026-10-02 JEG-86 REVIEWED: M3 worker correctly scoped (page puller + CSV filename guard). Reviewer fixed a real regression: guard validated raw --week, breaking --week N --ecr-type draft/dynasty (now validates effective week w; draft/dynasty stay week-0). Page puller verified against the LIVE FantasyPros page (slug + title + H1 all Week 4). 39/39 hermetic green. READY posted to Linear.
- 2026-10-02 JEG-101 M3 attempt 1 FAILED (no output): worker produced 65KB of thinking and zero files — analysis paralysis on a multi-constraint design task; exec reported "succeeded" with nothing committed. Attempt 2 dispatched with code-first constraints (no code in thinking blocks, 5-sentence planning cap, pre-validated design handed to it). If attempt 2 fails, JEG-101 goes to the Roman lane per the two-failure rule.

## The muse lane is active

The sweep doesn't just dispatch — it also executes `owner:muse` Todo issues
directly (subagents or inline), under the same WIP discipline. Roman is a working
lane, not just the dispatcher and reviewer.

## Usage watching

`lanes/usage.json` is written by the usage-watcher cron and read by the sweep
before every dispatch:
- per lane: quota remaining %, window reset time, last checked at
- the sweep never dispatches to a lane under 20% remaining — it reroutes
  (hard → muse; routine → waits for the next window)
- the morning digest shows per-lane usage bars; under 20% alerts Roman, never Jeremy

## Dispatch guard (enforced by the sweep)

1. Every brief declares `Required capabilities:` (one or more classes above).
2. The sweep refuses to dispatch a brief to a lane missing any required
   capability, and posts the refusal as a Linear comment naming the missing
   capability and the lane it routes to instead.
3. A task whose class is unclear is routed to `owner:muse` (Roman triages by
   hand) — never guessed into the minimax lane.

## Learning loop

If the minimax lane fails the same task class twice (loops, wrong-tool use,
hallucinated APIs), Roman adds the class to the blocklist below with the
evidence (issue links). The blocklist wins over the matrix.

### Blocklist (starts empty)

(none yet — entries need two failed issues as evidence)

## Direct-tasking reachability (JEG-94)

| origin lane | destination lane | status     | adapter          | notes                                              |
| ----------- | ---------------- | ---------- | ---------------- | -------------------------------------------------- |
| `minimax`   | `minimax`        | reachable  | `MiniMaxAdapter` | Self-dispatch — used for the JEG-94 dry-run demo.  |
| any lane    | `minimax`        | reachable  | `MiniMaxAdapter` | The only lane Muse can route to today.             |
| any lane    | `claude`         | NOT BUILT  | —                | The claude CLI was never verified working from Muse. Stop trying. |
| any lane    | `chatgpt`/`codex` | AVAILABLE | —                | Verified 2026-10-03: ChatGPT subscription OAuth + `codex exec` smoke probe OK. No adapter built yet (see KNOWN_LANES note below). |

`lanes/protocol.py::KNOWN_LANES` is `("minimax",)` — the protocol refuses
any lane name it does not know. To add a destination lane: implement
`LaneAdapter`, add the name to `KNOWN_LANES`, register a CLI under
`bin/<lane>`, wire its tests into `make test-unit`, and update the table
above. Do not extend `KNOWN_LANES` without also shipping an adapter.

Outbox/inbox paths (append-only; duplicates raise `LaneProtocolError`):

```
lanes/outbox/<dest_lane>/<issue>-<epoch>.json
lanes/inbox/<worker_lane>/<issue>-<epoch>.json
```

`epoch` is the unix timestamp of `created_at`. The inbox is a log, not a
mutable queue.
