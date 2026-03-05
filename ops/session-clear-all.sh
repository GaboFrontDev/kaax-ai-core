#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

set -a
if [[ -f ./.env ]]; then . ./.env; fi
if [[ -f ./.env.local ]]; then . ./.env.local; fi
set +a

uv run python - <<'PY'
import asyncio
import sys

sys.path.insert(0, ".")
import psycopg
from sql_utilities import get_database_url


async def main() -> None:
    url = get_database_url()
    async with await psycopg.AsyncConnection.connect(url, autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "TRUNCATE checkpoints, checkpoint_blobs, checkpoint_writes RESTART IDENTITY CASCADE"
            )
    print("All checkpoints deleted.")


asyncio.run(main())
PY
