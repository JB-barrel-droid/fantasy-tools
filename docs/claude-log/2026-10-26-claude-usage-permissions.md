## 2026-10-26 - Claude usage rules and repo permissions

Contract: cut per-turn token use and stop routine permission prompts, without changing site code or value logic. Approved by Jeremy 2026-10-26 ("Go ahead with all five").

### Verified (check named)
- `.claude/settings.json` parses (`python3 -c 'import json; json.load(open(".claude/settings.json"))'`).
- Only `CLAUDE.md`, `.claude/settings.json` and this log changed (`git diff --stat origin/main`).

### Claimed, not confirmed
- The allow/ask/deny rules match as intended in Claude Code 2.1.x; not exercised in a live session yet.
- Thread rotation now at ~200k (was 150k here; the user-level file still says 150k, and this repo rule overrides it).
