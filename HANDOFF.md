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
  A successor uses the same shape with its own name, e.g.
  `**<Agent> (Jeremy's AI PM)** — not written by Jeremy`.
- **Every question to Jeremy** carries a link, plain context and a
  recommendation. Batch questions; never re-ask one he has answered.
- **After any live deploy** tell him what to check, with a direct link to the
  exact page or tab under https://jb-barrel-droid.github.io/fantasy-tools/v2/.

## 3. Model routing and harness

- **Harness: Claude Code CLI** (`claude -p`), on every model (Jeremy, Oct 26:
  "Keep going with Claude code").
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
- **Non-Claude output** goes up as a draft PR for a Claude (T1) review
  (`AGENTS.md` rule 2).
- **Machines:**
  - *Mac mini:* checkout `~/code/fantasy-tools`, worktrees `~/code/wt/`. Claude
    is signed in; wrappers are in `~/.config/banana/`. macOS has no `setsid`, so
    detach runs with `nohup ... < /dev/null & disown`.
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
- **Budget:** `credits.sh` prints the OpenRouter balance from the credits
  endpoint. Trust it, not Claude Code's cost readout.
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

Last updated: Oct 26, 2026, 7:20 PM CT (by Ba-Nana).

**Active runs**
- Box: none running (checked with `ps`).
- Mac: unverified from here. Per Ba-Nana's notes, lane 4 CI tickets and the
  JEG-1121 Claude work live on the Mac, and a MiniMax run was finishing checks
  on [PR 963](https://github.com/JB-barrel-droid/fantasy-tools/pull/963).
  Check the Mac's `ps` and Linear In Progress before starting anything.

**Open PRs waiting on Jeremy**
- [PR 957](https://github.com/JB-barrel-droid/fantasy-tools/pull/957), [JEG-1121](https://linear.app/jegabee/issue/JEG-1121): review the movers / bench
  seats (A merge, B change, C rethink). A value-ordered seat rework was
  proposed and is being compared to a real ESPN std/12 league. Not merged.
- [PR 966](https://github.com/JB-barrel-droid/fantasy-tools/pull/966), [JEG-1115](https://linear.app/jegabee/issue/JEG-1115): fit-label option card; stays a draft.
- [PR 967](https://github.com/JB-barrel-droid/fantasy-tools/pull/967), [JEG-1134](https://linear.app/jegabee/issue/JEG-1134): two questions in the PR.
- [PR 968](https://github.com/JB-barrel-droid/fantasy-tools/pull/968), [JEG-885](https://linear.app/jegabee/issue/JEG-885): cap the first 10 only, or the whole list?
- [PR 969](https://github.com/JB-barrel-droid/fantasy-tools/pull/969) (JEG-894) and [PR 970](https://github.com/JB-barrel-droid/fantasy-tools/pull/970) (JEG-1101): copy questions on the tickets.
- [PR 958](https://github.com/JB-barrel-droid/fantasy-tools/pull/958) + [PR 960](https://github.com/JB-barrel-droid/fantasy-tools/pull/960): merge, then the one combined mcp deploy.
- Older and stale: [all open PRs](https://github.com/JB-barrel-droid/fantasy-tools/pulls)
  (959, 939, 925, 921, 920, 837; 962 has a merge conflict).

**Open decisions** (Linear label `needs-review`, team Jegabee):
JEG-1121, JEG-1115, JEG-1125 ("Even" band), JEG-1143 (findings),
JEG-1142 (parked behind JEG-1144).

**Next queued:** lane 4 tickets back in Todo for fresh DeepSeek runs; JEG-1144
research if Jeremy OKs it; research post refresh after PR 957 merges.

**OpenRouter balance:** $12.02 (`credits.sh`, Oct 26 7:20 PM CT).

## 6. Keeping this file current (anti-bloat)

- Update it whenever runs, PRs, decisions or rules change (the PM's 2-hourly
  check-in does this).
- Rewrite section 5 in place and bump "Last updated". Never append a log;
  history lives in git, Linear and the PRs.
- Delete anything resolved: merged PRs, answered decisions, finished runs.
- Link to Linear and GitHub; never copy their content here.
- Hard cap: about 150 lines and 10 KB for the file, about 40 lines for section 5.
  If an edit would go over, cut before adding.
