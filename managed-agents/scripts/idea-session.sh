#!/usr/bin/env bash
# On demand: open an idea-intake session and attach this terminal to it.
#   managed-agents/scripts/idea-session.sh ["first idea text"]
source "$(dirname "$0")/lib.sh"

SID=$(ant beta:sessions create --transform id -r --title "Idea intake" \
  --agent "$(AGENT_ID)" --environment-id "$(ENV_ID)" --vault-id "$(VAULT_ID)" \
  --resource "$(repo_resources | jq -c '.[0]')" \
  --budget "$(jq -nc --arg cents "$BUDGET_CENTS" '{type: "limit", max_list_cost: {amount: $cents, currency: "USD"}}')")

FIRST="Idea intake. Live dashboard: https://jb-barrel-droid.github.io/fantasy-tools/ . ${1:-Wait for my first idea.}"
ant beta:sessions:events send --session-id "$SID" \
  --event "$(jq -n --arg t "$FIRST" '{type: "user.message", content: [{type: "text", text: $t}]}')" >/dev/null
echo "Session $SID  https://platform.claude.com/workspaces/default/sessions/$SID"
exec ant beta:sessions connect "$SID"
