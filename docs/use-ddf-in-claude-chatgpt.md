# Use Data Driven Football in Claude and ChatGPT

How to connect the trade values to a chat assistant (JEG-1012, JEG-1024). Last updated 2026-10-24. Everything below is published by `make sync` from `app/llm/`; the MCP function itself is `supabase/functions/mcp/` (see `values-endpoint.md`).

## What you get

Ask in plain words ("who is worth more, Chase or Bijan, in a 10-team half-PPR superflex league?") and the assistant calls the tool with your league settings. Tools: `get_values`, `get_player_value`, `trade_targets`, `compare_trade`, `read_state`, `make_state`, `explain`. Every answer ends with a link to the same view on the site, and work moves both ways through the site link: press **Copy link** in the league row and paste the link into the chat; with the tool connected the assistant reads the league, rosters, trade and target from it (`read_state`) and continues. Ask it to save its work and it gives back a link (`make_state`); open it and the site shows what was applied and what was ignored. Without the tool connected, an assistant can still read the league settings in the link but not the players, which travel as site player numbers. Format: `design/llm-site-state.md`.

## Connect

- **Claude.ai / Claude Desktop:** Settings, Connectors, add a custom connector, URL `https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp`. No sign-in. Then add the skill: upload `ddf-skill.zip` from the site (`/ddf-skill.zip`) under Settings, Capabilities, Skills.
- **Claude Code:** `claude mcp add --transport http ddf https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp`, and copy `ddf-skill/SKILL.md` into `.claude/skills/data-driven-football/`.
- **ChatGPT (apps / developer mode):** add an MCP server with the same URL, no authentication. ChatGPT has no skills; the same guidance is in the server's own instructions, which the model reads on connect.
- **Custom GPT (Actions):** paste `/get-values.openapi.yaml`, authentication None. This route has the values only (no state tools), so the MCP route gives tighter answers.
- **Pointing an assistant at the site:** the page head links `llms.txt` (`<link rel="alternate" ... title="For AI assistants">`), which names the MCP URL, the skill and how to answer. A card is also at `/mcp-server-card.json` and `/.well-known/mcp/server-card.json`; the card format is a draft convention, so treat it as best effort. The `.well-known` copy sits under the project path, not the domain root, until the custom domain is live.

Plan and menu names change; check the vendor's connector docs if a step has moved.

## Limits

- Public and rate limited (60 requests a minute per IP for `mcp`, 30 for `get-values`). The first call after idle can take several seconds.
- The values endpoint prices the whole league: scoring, team count, roster shape, position shares, season weeks and advanced settings (JEG-1031). A custom league is computed per request, so its first answer takes about a second.
- A link carries the league (scoring, `teams`, roster shape) and your work: Find a trade rosters (`mine`, `theirs`), a Trade targets player (`target`) and the trade (`give`, `get`). Names an assistant gives that the site cannot match are listed on the page, never guessed.
- No prior-week "risers and fallers" yet (JEG-1029).
