#!/usr/bin/env bash
# One-time: load the vault from Keychain. Re-run after rotating a key (credentials are write-only).
source "$(dirname "$0")/lib.sh"
VAULT="$(VAULT_ID)"

mcp_bearer() { # name url keychain-service
  jq -n --arg n "$1" --arg u "$2" --arg t "$(keychain "$3")" \
    '{display_name: $n, auth: {type: "static_bearer", mcp_server_url: $u, token: $t}}' \
    | ant beta:vaults:credentials create --vault-id "$VAULT"
}
env_secret() { # name env-var host keychain-service
  jq -n --arg n "$1" --arg s "$2" --arg h "$3" --arg v "$(keychain "$4")" \
    '{display_name: $n, auth: {type: "environment_variable", secret_name: $s, secret_value: $v,
      networking: {type: "limited", allowed_hosts: [$h]}, injection_location: {header: true}}}' \
    | ant beta:vaults:credentials create --vault-id "$VAULT"
}

mcp_bearer "Linear" "https://mcp.linear.app/mcp" cma-linear
mcp_bearer "GitHub" "https://api.githubcopilot.com/mcp/" cma-github
env_secret "OpenRouter" OPENROUTER_API_KEY openrouter.ai cma-openrouter
env_secret "MiniMax" MINIMAX_API_KEY api.minimax.io cma-minimax
echo "Vault $VAULT loaded."
