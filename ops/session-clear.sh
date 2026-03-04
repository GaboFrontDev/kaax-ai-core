#!/usr/bin/env bash
set -euo pipefail

SESSION_ID_INPUT="${1:-${SESSION_ID:-}}"
if [[ -z "$SESSION_ID_INPUT" ]]; then
  echo "Usage: ./ops/session-clear.sh <session-id>" >&2
  echo "Or: SESSION_ID=<session-id> make session-clear" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
if [[ -f ./.env ]]; then
  . ./.env
fi
if [[ -f ./.env.local ]]; then
  . ./.env.local
fi
set +a

SESSION_ID="$SESSION_ID_INPUT" uv run python - <<'PY'
import asyncio
import os

from session_manager import SessionManager


async def main() -> None:
    session_id = os.environ["SESSION_ID"].strip()
    manager = SessionManager()
    try:
        await manager.start()
        await manager.adelete_thread(session_id)
        print(f"Deleted checkpoints for session_id={session_id}")
    finally:
        await manager.stop()


asyncio.run(main())
PY
