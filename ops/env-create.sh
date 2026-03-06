#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./ops/env-create.sh <env> <agent> [domain]

Purpose:
  Scaffold a new CDK env/agent entry in infra/cdk/config/environments.json.

Optional env vars:
  CONFIG_FILE        Path relative to infra/cdk (default: config/environments.json)
  TEMPLATE_ENV       Source env to clone defaults from (default: dev)
  TEMPLATE_AGENT     Source agent to clone defaults from (default: default)
  SERVICE_NAME       Override ECS service name (default: kaax-<env>-<agent>)
  SECRET_NAME        Override secret name (default: kaax/<env>/<agent>)
  PUBLIC_BASE_URL    Override public URL (default from [domain] -> https://<domain>)
  CERTIFICATE_ARN    Override ACM cert ARN for the new agent
  FORCE=true         Overwrite existing env/agent entry
  CREATE_SECRET=true Create empty AWS secret '{}' after JSON update
  AWS_REGION         Region for secret creation (fallback: env region, then us-east-1)

Examples:
  ./ops/env-create.sh dev clinicas clinicas.kaax.ai
  CREATE_SECRET=true ./ops/env-create.sh prod clinicas clinicas.kaax.ai
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ $# -lt 2 ]]; then
  usage >&2
  exit 1
fi

ENV_NAME="$1"
AGENT_NAME="$2"
DOMAIN="${3:-}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT_DIR/infra/cdk"
CONFIG_FILE="${CONFIG_FILE:-config/environments.json}"
CONFIG_PATH="$CDK_DIR/$CONFIG_FILE"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "Missing config file: $CONFIG_PATH" >&2
  echo "Create it from: $CDK_DIR/config/environments.example.json" >&2
  exit 1
fi

TEMPLATE_ENV="${TEMPLATE_ENV:-dev}"
TEMPLATE_AGENT="${TEMPLATE_AGENT:-default}"
SERVICE_NAME="${SERVICE_NAME:-kaax-${ENV_NAME}-${AGENT_NAME}}"
SECRET_NAME="${SECRET_NAME:-kaax/${ENV_NAME}/${AGENT_NAME}}"
PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"
if [[ -z "$PUBLIC_BASE_URL" && -n "$DOMAIN" ]]; then
  PUBLIC_BASE_URL="https://${DOMAIN}"
fi
CERTIFICATE_ARN="${CERTIFICATE_ARN:-}"
CREATE_SECRET="${CREATE_SECRET:-false}"
FORCE="${FORCE:-false}"

python3 - "$CONFIG_PATH" "$ENV_NAME" "$AGENT_NAME" "$TEMPLATE_ENV" "$TEMPLATE_AGENT" "$SERVICE_NAME" "$SECRET_NAME" "$PUBLIC_BASE_URL" "$CERTIFICATE_ARN" "$FORCE" <<'PY'
import copy
import json
import sys

config_path = sys.argv[1]
env_name = sys.argv[2]
agent_name = sys.argv[3]
template_env_name = sys.argv[4]
template_agent_name = sys.argv[5]
service_name = sys.argv[6]
secret_name = sys.argv[7]
public_base_url = sys.argv[8]
certificate_arn = sys.argv[9]
force = sys.argv[10].strip().lower() in {"1", "true", "yes", "on"}

with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)

template_env = data.get(template_env_name)
if not isinstance(template_env, dict):
    available = ", ".join(sorted(data.keys()))
    raise SystemExit(
        f"Template env '{template_env_name}' not found in {config_path}. Available: {available}"
    )

template_agents = template_env.get("agents")
if not isinstance(template_agents, dict) or not template_agents:
    raise SystemExit(f"Template env '{template_env_name}' has no agents to clone from")

if template_agent_name not in template_agents:
    template_agent_name = sorted(template_agents.keys())[0]

source_agent = template_agents[template_agent_name]
if not isinstance(source_agent, dict):
    raise SystemExit(
        f"Template agent '{template_agent_name}' in env '{template_env_name}' is invalid"
    )

if env_name not in data:
    data[env_name] = {
        "account": template_env.get("account"),
        "region": template_env.get("region"),
        "agents": {},
    }

env_obj = data[env_name]
if not isinstance(env_obj, dict):
    raise SystemExit(f"Target env '{env_name}' is not an object in config")

agents = env_obj.get("agents")
if not isinstance(agents, dict):
    env_obj["agents"] = {}
    agents = env_obj["agents"]

if agent_name in agents and not force:
    raise SystemExit(
        f"Target '{env_name}/{agent_name}' already exists. Re-run with FORCE=true to overwrite."
    )

new_agent = copy.deepcopy(source_agent)
new_agent["service_name"] = service_name
new_agent["secret_name"] = secret_name
new_agent.pop("secret_arn", None)

if public_base_url:
    new_agent["public_base_url"] = public_base_url
if certificate_arn:
    new_agent["certificate_arn"] = certificate_arn

environment = new_agent.get("environment")
if isinstance(environment, dict):
    environment["AUDRAI_DEPLOY_ENV"] = env_name

# Normalize to modern key names and make sure the minimal required keys exist.
legacy_keys = {
    "DB_DSN",
    "MODEL_NAME",
    "SMALL_MODEL",
    "PHONE_NUMBER_ID",
    "KNOWLEDGE_ADMIN_REQUESTORS",
}
required_keys = [
    "API_TOKENS",
    "DATABASE_URL",
    "AWS_REGION",
    "BEDROCK_MODEL",
    "DEFAULT_PROMPT_NAME",
    "WHATSAPP_META_VERIFY_TOKEN",
    "WHATSAPP_META_APP_SECRET",
    "WHATSAPP_META_ACCESS_TOKEN",
    "WHATSAPP_META_PHONE_NUMBER_ID",
]

raw_secret_keys = new_agent.get("secret_keys")
if not isinstance(raw_secret_keys, list):
    raw_secret_keys = []

secret_keys: list[str] = []
seen: set[str] = set()
for key in raw_secret_keys:
    k = str(key)
    if k in legacy_keys:
        continue
    if k not in seen:
        secret_keys.append(k)
        seen.add(k)

for key in required_keys:
    if key not in seen:
        secret_keys.append(key)
        seen.add(key)

new_agent["secret_keys"] = secret_keys
agents[agent_name] = new_agent

with open(config_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=True)
    f.write("\n")
PY

echo "Updated $CONFIG_PATH"
echo "Created/updated agent: ${ENV_NAME}/${AGENT_NAME}"
echo "service_name=${SERVICE_NAME}"
echo "secret_name=${SECRET_NAME}"
if [[ -n "$PUBLIC_BASE_URL" ]]; then
  echo "public_base_url=${PUBLIC_BASE_URL}"
fi

if [[ "$CREATE_SECRET" =~ ^(1|true|yes|on)$ ]]; then
  if ! command -v aws >/dev/null 2>&1; then
    echo "aws CLI not found; skipped secret creation." >&2
    exit 2
  fi

  REGION="${AWS_REGION:-}"
  if [[ -z "$REGION" ]]; then
    REGION="$(python3 - "$CONFIG_PATH" "$ENV_NAME" <<'PY'
import json
import sys

config_path = sys.argv[1]
env_name = sys.argv[2]
with open(config_path, "r", encoding="utf-8") as f:
    data = json.load(f)
env_obj = data.get(env_name, {})
region = env_obj.get("region", "")
print(region)
PY
)"
  fi
  REGION="${REGION:-us-east-1}"

  if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Secret already exists: ${SECRET_NAME} (${REGION})"
  else
    aws secretsmanager create-secret \
      --name "$SECRET_NAME" \
      --secret-string "{}" \
      --region "$REGION" >/dev/null
    echo "Created empty secret: ${SECRET_NAME} (${REGION})"
  fi
fi
