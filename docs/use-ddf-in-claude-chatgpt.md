# Use Data Driven Football in Claude and ChatGPT

How to connect the trade values to a chat assistant (JEG-1012). Status: written 2026-10-24 before the `mcp` function was deployed; the URLs below work only once it is (see `values-endpoint.md`).

## What you get

Ask in plain words ("who is worth more, Chase or Bijan in a 10-team half-PPR superflex league?") and the assistant calls the tool with your league settings. Tools: `get_values`, `get_player_value`, `trade_targets`, `compare_trade`, `explain`. Every answer names Data Driven Football and its as-of date.

## Claude

- **Claude.ai / Claude Desktop (connector):** Settings, Connectors, add a custom connector, URL `https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp`. No sign-in.
- **Claude Code:** `claude mcp add --transport http ddf https://iskiybsimubiujwuchsl.supabase.co/functions/v1/mcp`
- **Local stdio instead:** `mcp-server/` with `DDF_API_URL` set to the `get-values` URL.

## ChatGPT

- **Apps / developer mode:** add an MCP server with the same URL, no authentication.
- **Custom GPT (Actions):** paste `docs/get-values.openapi.yaml` into the GPT's Actions, authentication None. This route returns the whole list and the GPT does the lookup, so the MCP route gives tighter answers.

Plan and menu names change; check the vendor's current connector docs if a step has moved.

## Limits

Public and rate limited (60 requests a minute per IP for `mcp`, 30 for `get-values`). The first call after idle can take several seconds. No prior-week "risers and fallers" yet.
