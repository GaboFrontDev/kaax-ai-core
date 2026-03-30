"""DB helpers for conversation follow-up tracking."""

from __future__ import annotations

import logging

import psycopg

from sql_utilities import get_database_url

logger = logging.getLogger(__name__)


async def upsert_conversation(
    thread_id: str,
    phone_number: str,
    channel: str = "whatsapp",
) -> bool:
    """Record / refresh a conversation. Called on every inbound message.

    Returns True if this is a brand-new conversation (first message ever).
    """
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO conversations (thread_id, channel, phone_number, last_message_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (thread_id) DO UPDATE SET
                        last_message_at = NOW(),
                        phone_number = COALESCE(EXCLUDED.phone_number, conversations.phone_number)
                    RETURNING (xmax = 0) AS is_new
                    """,
                    (thread_id, channel, phone_number),
                )
                row = await cur.fetchone()
                return bool(row and row[0])
    except Exception:
        logger.exception("follow_up upsert_conversation failed thread=%s", thread_id)
        return False


async def mark_demo_requested(
    thread_id: str,
    contact_name: str | None = None,
) -> None:
    """Mark conversation so no follow-up is sent. Called when lead is captured."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET demo_requested = TRUE,
                    contact_name = COALESCE(%s, contact_name)
                WHERE thread_id = %s
                """,
                (contact_name, thread_id),
            )
    except Exception:
        logger.exception("follow_up mark_demo_requested failed thread=%s", thread_id)


async def get_pending_follow_ups() -> list[tuple[str, str, str | None]]:
    """Return (thread_id, phone_number, contact_name) for conversations needing follow-up."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT thread_id, phone_number, contact_name
                    FROM conversations
                    WHERE demo_requested = FALSE
                      AND follow_up_sent = FALSE
                      AND channel = 'whatsapp'
                      AND phone_number IS NOT NULL
                      AND last_message_at < NOW() - INTERVAL '2 hours'
                    """
                )
                return await cur.fetchall()
    except Exception:
        logger.exception("follow_up get_pending_follow_ups failed")
        return []


async def mark_follow_up_sent(thread_id: str) -> None:
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            await conn.execute(
                "UPDATE conversations SET follow_up_sent = TRUE WHERE thread_id = %s",
                (thread_id,),
            )
    except Exception:
        logger.exception("follow_up mark_follow_up_sent failed thread=%s", thread_id)


async def get_conversation_digest(lookback_hours: int = 24) -> list[dict]:
    """Return conversations active in the last `lookback_hours` for the digest report."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        thread_id,
                        phone_number,
                        contact_name,
                        memory_etapa,
                        memory_summary,
                        demo_requested,
                        follow_up_sent,
                        created_at,
                        last_message_at
                    FROM conversations
                    WHERE last_message_at >= NOW() - INTERVAL '%s hours'
                    ORDER BY last_message_at DESC
                    """,
                    (lookback_hours,),
                )
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in await cur.fetchall()]
    except Exception:
        logger.exception("get_conversation_digest failed")
        return []


async def get_conversation_memory(
    thread_id: str,
) -> tuple[str | None, str | None]:
    """Return (memory_summary, memory_etapa) for the given thread, or (None, None)."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT memory_summary, memory_etapa FROM conversations WHERE thread_id = %s",
                    (thread_id,),
                )
                row = await cur.fetchone()
                if row:
                    return row[0], row[1]
    except Exception:
        logger.exception("get_conversation_memory failed thread=%s", thread_id)
    return None, None


async def update_conversation_memory(
    thread_id: str,
    summary: str,
    etapa: str,
) -> None:
    """Persist a new memory summary after a funnel stage change."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            await conn.execute(
                """
                UPDATE conversations
                SET memory_summary = %s,
                    memory_etapa = %s,
                    memory_updated_at = NOW()
                WHERE thread_id = %s
                """,
                (summary, etapa, thread_id),
            )
    except Exception:
        logger.exception("update_conversation_memory failed thread=%s", thread_id)
