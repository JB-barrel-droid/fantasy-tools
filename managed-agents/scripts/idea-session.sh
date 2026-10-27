#!/usr/bin/env bash
# On demand: open an idea-intake session and attach this terminal to it.
#   managed-agents/scripts/idea-session.sh ["first idea text"]
source "$(dirname "$0")/lib.sh"

SID=$(jq -n --arg agent "$(AGENT_ID)" --arg env "$(ENV_ID)" --arg vault "$(VAULT_ID)" \
  --arg cents "$BUDGET_CENTS" --argjson res "$(repo_resources)" \
  '{agent: $agent, environment_id: $env, vault_ids: [$vault], resources: $res, title: "Idea intake",
    budget: {type: "limit", max_list_cost: {amount: $cents, currency: "USD"}}}' \
  | ant beta:sessions create --transform id -r)

FIRST="Idea intake. ${1:-Wait for my first idea.}"
ant beta:sessions:events send --session-id "$SID" \
  --event "$(jq -n --arg t "$FIRST" '{type: "user.message", content: [{type: "text", text: $t}]}')" >/dev/null
echo "Session $SID  https://platform.claude.com/workspaces/default/sessions/$SID"
exec ant beta:sessions connect "$SID"
