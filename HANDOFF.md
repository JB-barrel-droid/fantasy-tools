# Handoff: PM and lead for Data Driven Football

Read this first if you are taking over the PM/lead role from Ba-Nana (Grok Bot),
for example as Muse. `CLAUDE.md` (working agreements) and `AGENTS.md` (tiers,
board conventions) still apply and win on conflict; this file adds only what a
successor PM needs and the live state. Repo: JB-barrel-droid/fantasy-tools.

## 1. The role

You are Jeremy's full-time PM and lead for Data Driven Football, the
pre-launch trade-value site (live at https://jb-barrel-droid.github.io/fantasy-tools/v2/,
plan in Linear JEG-440). You own Linear: file, route, update and close tickets.
You drive headless coding runs (one per ticket), review their output, and bring
Jeremy decisions. You do not make big product decisions; he does (Oct 26).
Note: `CLAUDE.md` says "Muse owns nothing here". Taking over this role is
Jeremy's own ask (Oct 26), but merge and deploy rules below still hold.

## 2. How work flows

- **Linear is Jeremy's only progress view.** Team Jegabee, issue prefix `JEG`.
  Keep state in sync with reality (status meanings in `AGENTS.md`): In Progress
  only while a run is working it, In Review = waiting on Jeremy, Done = merged
  and live. Link every PR on its ticket and put "(JEG-xxx)" in the PR title.
- **Decisions:** add the `needs-review` label, move to In Review, and comment
  "Decision needed from Jeremy" with lettered options (A, B, C), plain context,
  and your recommendation. When he answers, quote him with the date, remove
  `needs-review`, move to Todo. A rule change also goes in `docs/decisions.md`.
- **Identity header.** The Linear connector posts as Jeremy's own account, so
  every comment starts with a header line saying who wrote it:
  `🍌 **Ba-Nana (Jeremy's AI PM)** — not written by Jeremy`, or for a run:
  `🍌 **Ba-Nana run (deepseek-v4.1-flash)** — not written by Jeremy`.
  A successor uses the same shape with its own name.
- **Run comments:** Started, then ✅ done or ❌ failed. Started and its ✅/❌ both
  carry `session: <machine>/<harness>/<id>`, e.g. `session: mac-mini/claude-code/65e6d78c`
  (`mac-mini`, `grok-box`, `hp-envy`; id = first 8 chars of Claude Code's `session_id`
  from `-p --output-format json`/`stream-json`, or Codex's session/thread id).
  One session on several tickets posts the same line on each.
- **Every question to Jeremy** carries a link, plain context and a
  recommendation. Batch questions; never re-ask one he has answered.
- **After any live deploy** tell him what to check, with a direct link to the
  exact page or tab under https://jb-barrel-droid.github.io/fantasy-tools/v2/.

## Working with Muse

- Label `muse` on a Linear ticket = Muse owns it; Ba-Nana doesn't pick it up. One owner per ticket.
- Muse comments on the ticket when it starts, with the PR link when done, and with any blockers.
- Branches are `muse/jeg-<id>-<slug>`; merge main in, never rebase or force-push; PRs aren't merged by Muse.

## 3. Model routing and harness

- **Harness: Claude Code CLI** (`claude -p`) on every model (Jeremy, Oct 26).
- **Cheap models** for tests, CSS, copy and small features:
  - OpenRouter `deepseek/deepseek-v4.1-flash` via the wrapper
    `~/.config/banana/claude-openrouter`. It sets `ANTHROPIC_BASE_URL=https://openrouter.ai/api`
    and `ANTHROPIC_AUTH_TOKEN` from `OPENROUTER_API_KEY`, pins every model slot
    to `BANANA_OR_MODEL` (default above), and unsets other keys.
  - MiniMax M3 via `~/.config/banana/claude-minimax` (Mac only) until the plan
    ends about Oct 31, 2026. This supersedes the "MiniMax is not used" line in
    `AGENTS.md` for these runs (Jeremy, Oct 26, in chat; not yet on a ticket).
- **Real Claude** (Jeremy's subscription) for value math and T1 review.
- **OpenAI** (`OPENAI_API_KEY`, about $5 budget) only for second-opinion reviews.
- **Cursor cloud agents** only for big self-contained jobs, and tell Jeremy first.
- **Non-Claude output** goes up as a draft PR for Claude (T1) review (`AGENTS.md` rule 2).
- **Machines:**
  - *Mac mini:* checkout `~/code/fantasy-tools`, worktrees `~/code/wt/`, Claude
    signed in, wrappers in `~/.config/banana/`; detach with `nohup ... < /dev/null & disown`.
  - *Linux box (grok-bot-vm):* clone `/workspace/code/fantasy-tools`, worktrees
    `/workspace/code/wt/<JEG-n>`, launchers and logs in `/workspace/logs/`
    (outside the repo; only Ba-Nana's box can see them).
- **Run pattern** (`/workspace/logs/run.sh <JEG-n>`):
  1. One worktree, one branch and one PR per ticket.
  2. Prompt file `prompts/<JEG-n>.md` (shared rules in `prompts/common.md`).
  3. `claude-openrouter -p "<prompt>" --output-format stream-json --verbose
     --max-turns 60 --dangerously-skip-permissions --disallowedTools
     "Bash(git push:*)" "Bash(gh:*)" "Bash(supabase:*)" "Bash(curl:*)"
     "Bash(env)" "Bash(printenv:*)"`, with `GITHUB_TOKEN GH_TOKEN
     OPENAI_API_KEY MINIMAX_API_KEY` unset. Log: `logs/banana-<JEG-n>-or.json`
     (+ `.err`).
  4. The run commits only. The PM reviews the diff and pushes, then opens the
     draft PR (`GITHUB_TOKEN`, fine-grained, this repo only).
  5. Out of turns: `resume.sh <JEG-n> <session-id> <n>` (finish-now prompt).
     `run-lane3.sh` is the same with 80 turns.
- **Budget:** trust `credits.sh` (OpenRouter balance), not Claude Code's cost readout.
- **Env var names only:** `OPENROUTER_API_KEY`, `MINIMAX_API_KEY`,
  `OPENAI_API_KEY`, `GITHUB_TOKEN`. Never print, echo or commit their values.

## 4. Standing rules (hard constraints)

- Runs never merge or deploy. Merges follow `AGENTS.md` and `runbooks/merging-prs.md`.
- Never deploy the mcp edge function, except the approved combined
  PR 958 + PR 960 deploy.
- No force-push, no history rewrite.
- PR 957 does not merge until Jeremy reviews its movers table.
- No risk-penalty logic until the JEG-1144 research lands.
- Never send PII or keys to model providers (training on prompts is fine).
- Don't touch the dirty generated files in the Mac checkout `~/code/fantasy-tools`.
- Don't stop, restart or move in-flight runs to make room for new ones.
- No big product decisions without Jeremy.

Product decisions to date (Oct 26 unless noted; details on the ticket):
- Bench value = league-wide bench VORP with a backup discount: [JEG-1121](https://linear.app/jegabee/issue/JEG-1121).
- Check a Trade: neutral verdict that names the Charted vs Projected gap,
  plus one limitation line per value: [JEG-1138](https://linear.app/jegabee/issue/JEG-1138).
- Paste-only league load at launch; the Sleeper/ESPN ID loader goes: [JEG-1131](https://linear.app/jegabee/issue/JEG-1131).
- The PMM doc is the copy direction (copy lands in [JEG-1130](https://linear.app/jegabee/issue/JEG-1130)).
  Value copy says "based on / starting from" a source, never "copied from".
- Design language in [PR 961](https://github.com/JB-barrel-droid/fantasy-tools/pull/961)
  is approved. Still open: Fraunces headline font, warm paper vs mint background.
- Research posts (JEG-545, JEG-557, JEG-925 / PR 837) get refreshed to the
  current rules and published without his review, after PR 957 merges, with a
  Claude accuracy check on the value-math claims.
- One headline DDF Value (trade-chart based); projections are shown with real
  numbers, never reduced to yes/no: [JEG-1073](https://linear.app/jegabee/issue/JEG-1073).

## 5. Current state

Last updated: Oct 27, 2026, 6:05 AM CT (by Ba-Nana).

**Merged overnight:** [PR 979](https://github.com/JB-barrel-droid/fantasy-tools/pull/979) and
[PR 984](https://github.com/JB-barrel-droid/fantasy-tools/pull/984) (main green again,
[JEG-1152](https://linear.app/jegabee/issue/JEG-1152) Done),
[PR 959](https://github.com/JB-barrel-droid/fantasy-tools/pull/959) (JEG-1119) and
[PR 957](https://github.com/JB-barrel-droid/fantasy-tools/pull/957) (bench seats, JEG-1121).

**Live problems:** [JEG-1156](https://linear.app/jegabee/issue/JEG-1156) (urgent, `needs-review`):
blended DDF Values blank until week-8 charts publish (A fallback to last week, recommended).
[JEG-1157](https://linear.app/jegabee/issue/JEG-1157) diagnosed: same cause (no week-8 charts,
get-values drops older weeks); the fix waits on the JEG-1156 choice.

**Running now** (all Mac, Claude Opus, merge wave 4 started 4:00 AM CT; launcher
`~/code/wt/merge-wave4.launch.sh`, state `/tmp/banana-merge-wave.state`, logs `/tmp/banana-w4-*.json`):
939+958, 921, 963, 920, 925, 962 (started 5:55 AM CT); 957 run is finishing its deploy watch.
Still queued: 964, 965, 967, 968, 973-975, 977, 978, 980, then Muse's 981 and 982.
Each waits for green main and merges under the merge lock.

**Held:** 976 (after 960), 960 (after 958, then the one combined mcp deploy),
969 (JEG-894 privacy line), 970 (JEG-1101 Copy link wording, asked), 966.

**Muse:** JEG-557 (PR 982) and JEG-1061 (PR 981) in review and queued to merge;
JEG-982 in progress; the numbered Muse queue on JEG-1145 has about 10 `muse` Todo tickets.

**Open decisions** (label `needs-review`): JEG-1156, JEG-1101, JEG-894, JEG-1115,
JEG-1125, JEG-1143, JEG-1142. QB bench count (8 vs about 7) is a low-priority math note.

**Next queued:** research post refresh (PR 957 merged); Codex JEG-1136 on
the HP once 921, 963, 964, 967, 939 merge.

## 6. Keeping this file current (anti-bloat)

- Update it whenever runs, PRs, decisions or rules change (2-hourly check-in).
- Rewrite section 5 in place and bump "Last updated". Never append a log;
  history lives in git, Linear and the PRs.
- Delete anything resolved (merged PRs, answered decisions, finished runs).
  Link to Linear and GitHub; never copy their content here.
- Hard cap: about 150 lines and 10 KB for the file, about 40 lines for section 5.
  If an edit would go over, cut before adding.
