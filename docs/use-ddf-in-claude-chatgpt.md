# Use Data Driven Football in Claude and ChatGPT

How to connect the trade values to a chat assistant (JEG-1012, JEG-1024). Last updated 2026-10-24. Everything below is published by `make sync` from `app/llm/`; the MCP function itself is `supabase/functions/mcp/` (see `values-endpoint.md`).

## What you get

Ask in plain words ("who is worth more, Chase or Bijan, in a 10-team half-PPR superflex league?") and the assistant calls the tool with your league settings. Tools: `get_values`, `get_player_value`, `trade_targets`, `compare_trade`, `read_state`, `make_state`, `explain`. Every answer ends with a link to the same view on the site, and work moves both ways: paste a `ddf-state` block from the site into the chat and the assistant continues from it; ask the assistant to save its work and paste the block (or open the link) on the site. Format: `design/llm-site-state.md`.

## Connect

- **Claude.ai / Claude Desktop:** Settings, Connectors, add a custom connector, URL `https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp`. No sign-in. Then add the skill: upload `ddf-skill.zip` from the site (`/ddf-skill.zip`) under Settings, Capabilities, Skills.
- **Claude Code:** `claude mcp add --transport http ddf https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp`, and copy `ddf-skill/SKILL.md` into `.claude/skills/data-driven-football/`.
- **ChatGPT (apps / developer mode):** add an MCP server with the same URL, no authentication. ChatGPT has no skills; the same guidance is in the server's own instructions, which the model reads on connect.
- **Custom GPT (Actions):** paste `/get-values.openapi.yaml`, authentication None. This route has the values only (no state tools), so the MCP route gives tighter answers.
- **Pointing an assistant at the site:** the page head links `llms.txt` (`<link rel="alternate" ... title="For AI assistants">`), which names the MCP URL, the skill and how to answer. A card is also at `/mcp-server-card.json` and `/.well-known/mcp/server-card.json`; the card format is a draft convention, so treat it as best effort. The `.well-known` copy sits under the project path, not the domain root, until the custom domain is live.

Plan and menu names change; check the vendor's connector docs if a step has moved.

## Limits

- Public and rate limited (60 requests a minute per IP for `mcp`, 30 for `get-values`). The first call after idle can take several seconds.
- The values endpoint prices scoring, team count and superflex. A league with a changed roster shape, position shares, season weeks or advanced settings is priced with the default lineup, and the assistant is told to say so (JEG-1029).
- Until the site reads `teams`, `mine`, `theirs` and `target` from a link (JEG-1026), a link for Find a trade or Trade targets opens the right tab but not the rosters or target.
- No prior-week "risers and fallers" yet (JEG-1029).
