# Shared helpers. Secrets come from macOS Keychain (service names below), never from files.
#   security add-generic-password -a "$USER" -s <service> -w   # prompts for the value
#   cma-github      fine-grained PAT on JB-barrel-droid/fantasy-tools: Contents RW, Pull requests RW, Actions R
#   cma-linear      Linear personal API key
#   cma-openrouter  OpenRouter key (set a credit limit on the OpenRouter side)
#   cma-minimax     MiniMax subscription API key
set -euo pipefail

# Retired 2026-10-27 (Jeremy, JEG-1173): every script here refuses to run, so nothing
# recreates the deployments or starts a session by accident.
if [[ "${CMA_ALLOW_RETIRED:-}" != "1" ]]; then
  echo "session:cma is retired (JEG-1173); managed-agents scripts are disabled." >&2
  exit 1
fi

MA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$MA_DIR/claude-lock.json"
REPO_URL="https://github.com/JB-barrel-droid/fantasy-tools"
BUDGET_CENTS="5000"

keychain() { security find-generic-password -a "$USER" -s "$1" -w; }
lock_id() { jq -er --arg k "$1" '.resources[$k].id' "$LOCK"; }

AGENT_ID() { lock_id "./agents/ddf-lead.md"; }
ENV_ID() { lock_id "./environments/ddf-cloud.yaml"; }
VAULT_ID() { lock_id "./vaults/ddf.yaml"; }

# Session/deployment resources: the repo mount. The token goes to Anthropic's git proxy, never into the sandbox.
repo_resources() {
  jq -n --arg url "$REPO_URL" --arg tok "$(keychain cma-github)" \
    '[{type: "github_repository", url: $url, authorization_token: $tok, mount_path: "/workspace/fantasy-tools"}]'
}
