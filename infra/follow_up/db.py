"""DB helpers for conversation follow-up tracking."""

from __future__ import annotations

import logging

import psycopg

from sql_utilities import get_database_url

logger = logging.getLogger(__name__)

CONTROL_MESSAGE_PREFIX = "[[control:"
HANDOFF_RELEASED_CONTROL = "[[control:handoff_released]]"


def is_control_message(content: str) -> bool:
    return content.startswith(CONTROL_MESSAGE_PREFIX)


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


def _decode_checkpoint_messages(blob: bytes, last_n: int = 6) -> list[tuple[str, str]]:
    """Decode a LangGraph msgpack messages blob. Returns list of (role, content)."""
    try:
        import ormsgpack

        def _ext(code, data):  # noqa: ANN001
            return data

        raw_list = ormsgpack.unpackb(blob, ext_hook=_ext)
        results = []
        for item in raw_list:
            if not isinstance(item, bytes):
                continue
            try:
                parts = ormsgpack.unpackb(item, ext_hook=_ext)
                if isinstance(parts, (list, tuple)) and len(parts) >= 3:
                    fields = parts[2]
                    if isinstance(fields, dict):
                        role = fields.get(b"type") or fields.get("type")
                        content = fields.get(b"content") or fields.get("content")
                        if isinstance(role, bytes):
                            role = role.decode()
                        if isinstance(content, bytes):
                            content = content.decode()
                        if role in ("human", "ai") and isinstance(content, str) and content.strip():
                            results.append((role, content))
            except Exception:
                pass
        return results[-last_n:]
    except Exception:
        return []


async def get_conversation_digest(lookback_hours: int = 24) -> list[dict]:
    """Return conversations active in the last `lookback_hours` for the digest report."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        c.thread_id,
                        c.phone_number,
                        c.contact_name,
                        c.memory_etapa,
                        c.memory_summary,
                        c.demo_requested,
                        c.follow_up_sent,
                        c.created_at,
                        c.last_message_at,
                        cb.blob AS messages_blob
                    FROM conversations c
                    LEFT JOIN LATERAL (
                        SELECT blob FROM checkpoint_blobs
                        WHERE thread_id = c.thread_id
                          AND channel = 'messages'
                        ORDER BY version DESC
                        LIMIT 1
                    ) cb ON TRUE
                    WHERE c.last_message_at >= NOW() - (%s * INTERVAL '1 hour')
                    ORDER BY c.last_message_at DESC
                    """,
                    (lookback_hours,),
                )
                rows = await cur.fetchall()
                cols = [d.name for d in cur.description]
                result = []
                for row in rows:
                    d = dict(zip(cols, row))
                    blob = d.pop("messages_blob", None)
                    d["last_messages"] = _decode_checkpoint_messages(blob) if blob else []
                    result.append(d)
                return result
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


async def get_handoff_requested(thread_id: str) -> bool:
    """Return whether the conversation is currently assigned to human handoff."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT handoff_requested FROM conversations WHERE thread_id = %s",
                    (thread_id,),
                )
                row = await cur.fetchone()
                return bool(row and row[0])
    except Exception:
        logger.exception("get_handoff_requested failed thread=%s", thread_id)
        return False


async def set_handoff_requested(thread_id: str, active: bool) -> bool:
    """Set handoff_requested and return True only when the value changed."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE conversations
                    SET handoff_requested = %s
                    WHERE thread_id = %s
                      AND COALESCE(handoff_requested, FALSE) IS DISTINCT FROM %s
                    RETURNING thread_id
                    """,
                    (active, thread_id, active),
                )
                row = await cur.fetchone()
                return bool(row)
    except Exception:
        logger.exception(
            "set_handoff_requested failed thread=%s active=%s",
            thread_id,
            active,
        )
        return False


async def get_recent_messages(thread_id: str, limit: int = 6) -> list[tuple[str, str]]:
    """Return the most recent persisted messages in chronological order."""
    safe_limit = max(1, limit)
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT role, content
                    FROM conversation_messages
                    WHERE thread_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (thread_id, safe_limit),
                )
                rows = await cur.fetchall()
                rows.reverse()
                return [(str(role), str(content)) for role, content in rows]
    except Exception:
        logger.exception("get_recent_messages failed thread=%s", thread_id)
        return []


async def save_control_message(thread_id: str, content: str) -> None:
    """Persist an internal control marker in the conversation timeline."""
    await save_message(thread_id, "admin", content)


async def save_message(thread_id: str, role: str, content: str) -> None:
    """Persist a conversation message (human, agent, or admin)."""
    url = get_database_url()
    try:
        async with await psycopg.AsyncConnection.connect(url) as conn:
            await conn.execute(
                "INSERT INTO conversation_messages (thread_id, role, content) VALUES (%s, %s, %s)",
                (thread_id, role, content),
            )
    except Exception:
        logger.exception("save_message failed thread=%s role=%s", thread_id, role)
