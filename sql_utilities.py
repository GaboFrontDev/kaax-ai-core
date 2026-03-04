"""Minimal SQL helpers for LangGraph checkpoints."""

from __future__ import annotations

import logging

import psycopg
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
        min_size=1,
        max_size=10,
        timeout=30.0,
        open=False,
    )
    logger.info("Async PostgreSQL connection pool created")
    return pool


async def setup_postgres_checkpointer_tables_async(checkpointer) -> bool:
    """Initialize LangGraph checkpoint tables, with advisory lock for concurrency safety."""
    setup_lock_id = 12345678
    database_url = get_database_url()

    try:
        async with await psycopg.AsyncConnection.connect(database_url, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT pg_try_advisory_lock(%s)", (setup_lock_id,))
                result = await cur.fetchone()
                lock_acquired = result[0]

                if not lock_acquired:
                    logger.info("Waiting for another process to finish checkpoint table setup")
                    await cur.execute("SELECT pg_advisory_lock(%s)", (setup_lock_id,))

                try:
                    await cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_schema = 'public' AND table_name = 'checkpoints'
                        )
                        """
                    )
                    exists = (await cur.fetchone())[0]

                    if exists:
                        logger.debug("Checkpoint tables already exist")
                    else:
                        logger.info("Creating checkpoint tables")
                        await checkpointer.setup()
                finally:
                    await cur.execute("SELECT pg_advisory_unlock(%s)", (setup_lock_id,))

        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to setup checkpoint tables: %s", exc)
        return False
