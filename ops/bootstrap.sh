#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CDK_DIR="$ROOT_DIR/infra/cdk"
REGION="${AWS_REGION:-us-east-1}"
CDK_VENV_DIR="$CDK_DIR/.venv"
PYVENV_CFG="$CDK_VENV_DIR/pyvenv.cfg"

if ! command -v aws >/dev/null 2>&1; then
  echo "aws CLI not found. Install awscli first." >&2
  exit 1
fi

if ! command -v cdk >/dev/null 2>&1; then
  echo "cdk CLI not found. Install with: npm i -g aws-cdk" >&2
  exit 1
fi

if [[ ! -d "$CDK_DIR" ]]; then
  echo "Missing CDK directory: $CDK_DIR" >&2
  exit 1
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"

if [[ -f "$PYVENV_CFG" ]]; then
  expected_marker="$CDK_VENV_DIR"
  if ! grep -Fq "$expected_marker" "$PYVENV_CFG"; then
    echo "Detected stale CDK virtualenv at $CDK_VENV_DIR. Recreating it..."
    rm -rf "$CDK_VENV_DIR"
  fi
fi

python3 -m venv "$CDK_VENV_DIR"
source "$CDK_VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r "$CDK_DIR/requirements.txt"

cd "$ROOT_DIR"
cdk bootstrap "aws://${ACCOUNT_ID}/${REGION}"

echo "CDK bootstrapped for aws://${ACCOUNT_ID}/${REGION}"
