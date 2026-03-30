"""Conversation digest scheduler.

Runs every DIGEST_INTERVAL_HOURS and sends a WhatsApp summary of recent
conversations to WHATSAPP_NOTIFY_TO.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from infra.follow_up.db import get_conversation_digest
from settings import (
    DIGEST_INTERVAL_HOURS,
    DIGEST_LOOKBACK_HOURS,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_PHONE_NUMBER_ID,
    WHATSAPP_NOTIFY_TO,
)

logger = logging.getLogger(__name__)

_ETAPA_LABELS = {
    "discovery": "🔍 Discovery",
    "qualification": "📊 Calificación",
    "capture": "🎯 Captura",
    "cierre": "✅ Cierre",
    "knowledge": "💡 Conocimiento",
}


def _time_ago(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)
    if hours >= 24:
        return f"hace {hours // 24}d"
    if hours > 0:
        return f"hace {hours}h"
    return f"hace {minutes}m"


def _build_digest(conversations: list[dict], lookback_hours: int) -> list[str]:
    """Build WhatsApp message(s) for the digest. Splits if too long."""
    total = len(conversations)
    demo_count = sum(1 for c in conversations if c.get("demo_requested"))

    header = (
        f"📊 *Resumen de conversaciones — Kaax AI*\n"
        f"🗓️ Últimas {lookback_hours}h: *{total}* conversación(es) | "
        f"🎯 Demo solicitada: *{demo_count}*\n"
        f"{'─' * 30}"
    )

    blocks = [header]
    for i, conv in enumerate(conversations, 1):
        name = conv.get("contact_name") or "Desconocido"
        phone = conv.get("phone_number") or "—"
        etapa = conv.get("memory_etapa") or "—"
        etapa_label = _ETAPA_LABELS.get(etapa, f"📌 {etapa}")
        summary = conv.get("memory_summary") or "Sin resumen aún"
        demo = "✅ Sí" if conv.get("demo_requested") else "❌ No"
        last = _time_ago(conv["last_message_at"]) if conv.get("last_message_at") else "—"

        snippet = summary[:200] + ("…" if len(summary) > 200 else "")
        block = (
            f"\n*{i}. {name}*\n"
            f"📱 {phone}\n"
            f"Etapa: {etapa_label} | Demo: {demo}\n"
            f"Último mensaje: {last}\n"
            f"_{snippet}_"
        )
        blocks.append(block)

    # Split into chunks of max 4000 chars
    messages: list[str] = []
    current = ""
    for block in blocks:
        if len(current) + len(block) > 3900:
            if current:
                messages.append(current.strip())
            current = block
        else:
            current += "\n" + block
    if current:
        messages.append(current.strip())

    return messages


async def _run_once() -> None:
    if not DIGEST_INTERVAL_HOURS:
        return
    if not WHATSAPP_NOTIFY_TO or not WHATSAPP_META_ACCESS_TOKEN or not WHATSAPP_META_PHONE_NUMBER_ID:
        logger.debug("digest_scheduler: credentials or WHATSAPP_NOTIFY_TO not set, skipping")
        return

    from infra.whatsapp_meta.client import send_meta_text_message

    conversations = await get_conversation_digest(lookback_hours=DIGEST_LOOKBACK_HOURS)

    if not conversations:
        logger.info("digest_scheduler: no conversations in last %dh", DIGEST_LOOKBACK_HOURS)
        return

    messages = _build_digest(conversations, DIGEST_LOOKBACK_HOURS)
    for msg in messages:
        try:
            await send_meta_text_message(
                api_version=WHATSAPP_META_API_VERSION,
                phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
                access_token=WHATSAPP_META_ACCESS_TOKEN,
                to=WHATSAPP_NOTIFY_TO,
                text=msg,
            )
        except Exception:
            logger.exception("digest_scheduler: failed to send message")

    logger.info(
        "digest_scheduler: sent %d message(s) covering %d conversation(s)",
        len(messages), len(conversations),
    )


async def run_digest_scheduler() -> None:
    if not DIGEST_INTERVAL_HOURS:
        logger.info("digest_scheduler: disabled (DIGEST_INTERVAL_HOURS=0)")
        return

    interval = DIGEST_INTERVAL_HOURS * 3600
    logger.info(
        "digest_scheduler started (interval=%dh, lookback=%dh)",
        DIGEST_INTERVAL_HOURS, DIGEST_LOOKBACK_HOURS,
    )
    while True:
        await asyncio.sleep(interval)
        try:
            await _run_once()
        except Exception:
            logger.exception("digest_scheduler unexpected error")
