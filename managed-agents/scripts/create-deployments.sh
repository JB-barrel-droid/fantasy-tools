#!/usr/bin/env bash
# One-time: create the scheduled deployments. Created here, not by ant apply, because the
# repo mount's token must come from Keychain at create time. Prints the deployment IDs.
source "$(dirname "$0")/lib.sh"

deploy() { # name cron message
  ant beta:deployments create --transform id -r \
    --name "$1" --agent "$(AGENT_ID)" --environment-id "$(ENV_ID)" --vault-id "$(VAULT_ID)" \
    --resource "$(repo_resources | jq -c '.[0]')" \
    --schedule "$(jq -nc --arg cron "$2" '{type: "cron", expression: $cron, timezone: "America/Chicago"}')" \
    --budget "$(jq -nc --arg cents "$BUDGET_CENTS" '{type: "limit", max_list_cost: {amount: $cents, currency: "USD"}}')" \
    --initial-event "$(jq -nc --arg msg "$3" '{type: "user.message", content: [{type: "text", text: $msg}]}')"
}

deploy "ddf-queue" "0 * * * *" \
  "Queue run. Live dashboard: https://jb-barrel-droid.github.io/fantasy-tools/ . Do board hygiene, take back idle tickets, work up to 5 tickets in parallel per your instructions, then append your line to the CMA usage log."
deploy "ddf-weekly-usage" "0 7 * * 1" \
  "Weekly usage review. Read the last 7 days of the Linear document 'CMA usage log' and the merged PRs and closed tickets for the week. Add a dated section to the Linear document 'CMA weekly usage' in project Trade Value Chart: runs by outcome, tickets closed per run, what was delegated or outsourced and to which model, where tokens were wasted, and up to 3 concrete changes to routing, cadence or prompts, each as a needs-review ticket for Jeremy. Do not take a queue ticket."
