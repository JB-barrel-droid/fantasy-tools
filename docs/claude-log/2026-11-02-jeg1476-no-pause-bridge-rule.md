# 2026-11-02 · JEG-1476 · Rule: never pause or kill bridge processes

Ticket: JEG-1476 (child of JEG-1444). Session: charter thread, cloud.

## What changed
- `AGENTS.md`, Standing constraints: new rule that no agent signals, suspends,
  renices or kills a bridge process or its child test processes. An agent
  reports the PID, command and ticket and asks Jeremy instead.
- Follow-up commit: one sentence saying test code may still stop the fixture
  processes its own test run started. Two Codex jobs read the first wording as
  forbidding the bridge test suite's own fixture cleanup and stopped before
  running it (JEG-1422, JEG-1471, 03:16 UTC).

## Why
On 2026-11-01 at 7:58 PM CT, a Codex Desktop chat asked to stop a flashing
Chrome icon sent SIGSTOP to the bridge's Codex app-server (PID 1422) and two
Claude workers. Every Codex start timed out for 23 minutes, and four jobs froze
until SIGCONT at 02:21 UTC on Nov 2. Jeremy picked A on Nov 2 at 02:31 UTC:
add a rule that Codex never pauses or kills bridge processes. The bridge
folder guard blocks agents from writing the global `~/.codex/AGENTS.md`.
Jeremy, 02:46 UTC: "Have Claude do it. I'm not at my computer. Figure it
outs". So the rule goes into the repo's own AGENTS.md here and in
agent-bridge.

## Verified (check named)
- `git diff --stat`: one AGENTS.md paragraph and this log; no code changed.

## Claimed, not confirmed
- The repo-level file covers Codex and Claude sessions whose working
  directory is inside this repo. The Nov 1 chat ran in
  `~/Documents/Codex/2026-11-01/chro`, outside any repo, so only the global
  `~/.codex/AGENTS.md` would have reached it. That file waits for Jeremy at
  the Mac.
