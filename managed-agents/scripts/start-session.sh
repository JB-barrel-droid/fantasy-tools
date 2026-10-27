#!/usr/bin/env bash
# Start a one-off session without attaching, e.g.:
#   managed-agents/scripts/start-session.sh "Board cleanup" "Board cleanup."
source "$(dirname "$0")/lib.sh"

SID=$(ant beta:sessions create --transform id -r --title "$1" \
  --agent "$(AGENT_ID)" --environment-id "$(ENV_ID)" --vault-id "$(VAULT_ID)" \
  --resource "$(repo_resources | jq -c '.[0]')" \
  --budget "$(jq -nc --arg cents "$BUDGET_CENTS" '{type: "limit", max_list_cost: {amount: $cents, currency: "USD"}}')")
ant beta:sessions:events send --session-id "$SID" \
  --event "$(jq -n --arg t "$2" '{type: "user.message", content: [{type: "text", text: $t}]}')" >/dev/null
echo "$SID https://platform.claude.com/workspaces/default/sessions/$SID"
