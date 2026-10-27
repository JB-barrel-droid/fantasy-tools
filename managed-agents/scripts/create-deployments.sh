#!/usr/bin/env bash
# One-time: create the scheduled deployments. Created here, not by ant apply, because the
# repo mount's token must come from Keychain at create time. Prints the deployment IDs.
source "$(dirname "$0")/lib.sh"

deploy() { # name cron message
  jq -n --arg name "$1" --arg cron "$2" --arg msg "$3" \
    --arg agent "$(AGENT_ID)" --arg env "$(ENV_ID)" --arg vault "$(VAULT_ID)" \
    --arg cents "$BUDGET_CENTS" --argjson res "$(repo_resources)" \
    '{name: $name, agent: $agent, environment_id: $env, vault_ids: [$vault], resources: $res,
      schedule: {type: "cron", expression: $cron, timezone: "America/Chicago"},
      budget: {type: "limit", max_list_cost: {amount: $cents, currency: "USD"}},
      initial_events: [{type: "user.message", content: [{type: "text", text: $msg}]}]}' \
    | ant beta:deployments create --transform id -r
}

deploy "ddf-queue" "0 */2 * * *" \
  "Queue run. Work the session:cma queue per your instructions, then append your line to the CMA usage log."
deploy "ddf-weekly-usage" "0 7 * * 1" \
  "Weekly usage review. Read the last 7 days of the Linear document 'CMA usage log' and the merged PRs and closed tickets for the week. Add a dated section to the Linear document 'CMA weekly usage' in project Trade Value Chart: runs by outcome, tickets closed per run, what was delegated or outsourced and to which model, where tokens were wasted, and up to 3 concrete changes to routing, cadence or prompts, each as a needs-review ticket for Jeremy. Do not take a queue ticket."
