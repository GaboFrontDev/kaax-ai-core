"""Minimal SQL helpers for LangGraph checkpoints."""

from __future__ import annotations

import logging

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from settings import DATABASE_URL, DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

logger = logging.getLogger(__name__)



def get_database_url() -> str:
    if DATABASE_URL:
        return DATABASE_URL
    return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


async def test_database_connection_async() -> bool:
    try:
        database_url = get_database_url()
        async with await psycopg.AsyncConnection.connect(database_url) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                await cur.fetchone()
        logger.info("Database connection test successful")
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Database connection test failed: %s", exc)
        return False



def create_async_postgres_connection_pool() -> AsyncConnectionPool:
    database_url = get_database_url()
    pool = AsyncConnectionPool(
        conninfo=database_url,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        min_size=1,
        max_size=10,
        timeout=30.0,
        open=False,
    )
    logger.info("Async PostgreSQL connection pool created")
    return pool


async def setup_postgres_checkpointer_tables_async(checkpointer) -> bool:  # noqa: ARG001
    """Initialize LangGraph checkpoint tables.

    Uses a temporary AsyncPostgresSaver with its own autocommit connection so that
    CREATE INDEX CONCURRENTLY (which cannot run inside a transaction) succeeds.
    Advisory locks were removed because pgBouncer session-mode poolers keep sessions
    alive across restarts, causing pg_advisory_lock to hang indefinitely.
    The `checkpointer` argument is kept for API compatibility but is not used.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        database_url = get_database_url()
        async with AsyncPostgresSaver.from_conn_string(database_url) as tmp:
            await tmp.setup()
        logger.info("Checkpoint tables ready")
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to setup checkpoint tables: %s", exc)
        return False
