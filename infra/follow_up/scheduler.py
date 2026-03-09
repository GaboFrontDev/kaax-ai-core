"""Follow-up scheduler: every 30 min checks for conversations without demo after 2 h."""

from __future__ import annotations

import asyncio
import logging

from infra.follow_up.db import get_pending_follow_ups, mark_follow_up_sent
from settings import (
    FOLLOW_UP_MESSAGE,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_PHONE_NUMBER_ID,
)

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 30 * 60  # 30 minutes


async def _run_once() -> None:
    if not WHATSAPP_META_ACCESS_TOKEN or not WHATSAPP_META_PHONE_NUMBER_ID:
        logger.debug("follow_up scheduler: Meta credentials not configured, skipping")
        return

    from infra.whatsapp_meta.client import send_meta_text_message

    pending = await get_pending_follow_ups()
    if not pending:
        return

    logger.info("follow_up: %d conversation(s) pending follow-up", len(pending))

    for thread_id, phone_number, contact_name in pending:
        try:
            name_part = f" {contact_name}" if contact_name else ""
            message = FOLLOW_UP_MESSAGE.format(name=name_part)
            await send_meta_text_message(
                api_version=WHATSAPP_META_API_VERSION,
                phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
                access_token=WHATSAPP_META_ACCESS_TOKEN,
                to=phone_number,
                text=message,
            )
            await mark_follow_up_sent(thread_id)
            logger.info("follow_up sent to=%s thread=%s", phone_number, thread_id)
        except Exception:
            logger.exception("follow_up failed to=%s thread=%s", phone_number, thread_id)


async def run_scheduler() -> None:
    logger.info("follow_up scheduler started (interval=%ds, trigger=2h inactivity)", _CHECK_INTERVAL)
    while True:
        await asyncio.sleep(_CHECK_INTERVAL)
        try:
            await _run_once()
        except Exception:
            logger.exception("follow_up scheduler unexpected error")
