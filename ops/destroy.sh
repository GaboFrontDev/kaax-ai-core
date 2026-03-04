#!/usr/bin/env bash
set -euo pipefail

ENV_NAME="${1:-dev}"
AGENT_NAME="${2:-default}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT_DIR/infra/cdk"
CONFIG_FILE="${CONFIG_FILE:-config/environments.json}"
CDK_VENV_DIR="$CDK_DIR/.venv"
PYVENV_CFG="$CDK_VENV_DIR/pyvenv.cfg"

if [[ ! -f "$CDK_DIR/$CONFIG_FILE" ]]; then
  echo "Missing $CDK_DIR/$CONFIG_FILE" >&2
  echo "Create it from: $CDK_DIR/config/environments.example.json" >&2
  exit 1
fi

venv_needs_bootstrap() {
  if [[ ! -d "$CDK_VENV_DIR" ]]; then
    return 0
  fi
  if [[ ! -f "$PYVENV_CFG" ]]; then
    return 0
  fi
  if ! grep -Fq "$CDK_VENV_DIR" "$PYVENV_CFG"; then
    return 0
  fi
  return 1
}

if venv_needs_bootstrap; then
  "$ROOT_DIR/ops/bootstrap.sh"
fi

source "$CDK_VENV_DIR/bin/activate"
cd "$CDK_DIR"

cdk destroy --force \
  -c config="$CONFIG_FILE" \
  -c env="$ENV_NAME" \
  -c agent="$AGENT_NAME"
