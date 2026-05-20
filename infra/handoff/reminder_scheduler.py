"""Handoff reminder scheduler (WhatsApp).

Every minute, scans for open handoffs whose latest notification was sent more
than `HANDOFF_REMINDER_MINUTES` ago without an admin reply, and pings the owner
again on WhatsApp. Stops at `HANDOFF_REMINDER_MAX`.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from infra.follow_up.db import (
    get_recent_messages,
    get_stale_handoffs,
    mark_handoff_notified,
)
from infra.whatsapp_meta.client import send_meta_text_message
from settings import (
    HANDOFF_REMINDER_MAX,
    HANDOFF_REMINDER_MINUTES,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_PHONE_NUMBER_ID,
    WHATSAPP_NOTIFY_TO,
)

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 60  # seconds


def _minutes_since(ts: datetime | None) -> int:
    if not ts:
        return 0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    return max(0, int(delta.total_seconds() // 60))


def _format_history(messages: list[tuple[str, str]], limit: int = 4) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for role, content in messages[-limit:]:
        prefix = "👤" if role in ("user", "human") else "🤖"
        snippet = content if len(content) <= 100 else f"{content[:100]}…"
        lines.append(f"{prefix} {snippet}")
    return "\n".join(lines)


def _build_reminder_text(
    *,
    phone_number: str,
    minutes_waiting: int,
    reminder_number: int,
    last_user_message: str,
    recent_messages: list[tuple[str, str]],
) -> str:
    truncated = (
        last_user_message
        if len(last_user_message) <= 200
        else f"{last_user_message[:200]}…"
    )
    parts = [
        f"⏰ Recordatorio #{reminder_number} — handoff sin responder",
        f"Lleva {minutes_waiting} min esperando.",
        f"Número: {phone_number}",
        "",
        f'Último mensaje: "{truncated}"',
    ]
    history = _format_history(recent_messages)
    if history:
        parts.append("")
        parts.append("Historial reciente:")
        parts.append(history)
    return "\n".join(parts)


async def _run_once() -> None:
    if not WHATSAPP_NOTIFY_TO or not WHATSAPP_META_ACCESS_TOKEN:
        return
    if not WHATSAPP_META_PHONE_NUMBER_ID:
        return

    stale = await get_stale_handoffs(
        stale_after_minutes=HANDOFF_REMINDER_MINUTES,
        max_reminders=HANDOFF_REMINDER_MAX,
    )
    if not stale:
        return

    logger.info("handoff_reminder: %d stale handoff(s) pending", len(stale))

    for row in stale:
        thread_id = row["thread_id"]
        try:
            recent = await get_recent_messages(thread_id, limit=6)
            last_user = next(
                (
                    content
                    for role, content in reversed(recent)
                    if role in ("user", "human")
                ),
                "",
            )
            minutes_waiting = _minutes_since(row["handoff_notified_at"])
            reminder_number = int(row["handoff_reminders_sent"]) + 1

            text = _build_reminder_text(
                phone_number=row["phone_number"],
                minutes_waiting=minutes_waiting,
                reminder_number=reminder_number,
                last_user_message=last_user,
                recent_messages=recent,
            )
            await send_meta_text_message(
                api_version=WHATSAPP_META_API_VERSION,
                phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
                access_token=WHATSAPP_META_ACCESS_TOKEN,
                to=WHATSAPP_NOTIFY_TO,
                text=text,
            )
            await mark_handoff_notified(thread_id)
            logger.info(
                "handoff_reminder sent thread=%s #%d after=%dmin",
                thread_id,
                reminder_number,
                minutes_waiting,
            )
        except Exception:
            logger.exception("handoff_reminder failed thread=%s", thread_id)


async def run_handoff_reminder_scheduler() -> None:
    logger.info(
        "handoff reminder scheduler started (interval=%ds, delay=%dmin, max=%d)",
        _CHECK_INTERVAL,
        HANDOFF_REMINDER_MINUTES,
        HANDOFF_REMINDER_MAX,
    )
    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            await _run_once()
        except Exception:
            logger.exception("handoff_reminder scheduler unexpected error")
