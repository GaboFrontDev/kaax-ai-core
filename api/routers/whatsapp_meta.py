"""WhatsApp Meta webhook router."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from api.agent_service import AgentService
from api.dependencies import get_agent_service
from api.handlers import process_request
from infra.adapters import AdapterNotConfiguredError, get_whatsapp_adapter
from infra.follow_up.db import upsert_conversation
from infra.whatsapp_meta.client import download_media, send_meta_text_message, send_typing_action
from infra.whatsapp_meta.webhook import (
    validate_meta_signature,
    verify_meta_webhook_token,
)
from infra.deepgram.client import transcribe as deepgram_transcribe
from settings import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_STT_LANGUAGE,
    DEEPGRAM_STT_MODEL,
    WHATSAPP_PROVIDER,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_APP_SECRET,
    WHATSAPP_META_MODEL_NAME,
    WHATSAPP_META_PHONE_NUMBER_ID,
    WHATSAPP_META_PROMPT_NAME,
    WHATSAPP_META_TEMPERATURE,
    WHATSAPP_META_VERIFY_TOKEN,
    WHATSAPP_NOTIFY_TO,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-session lock: serializes concurrent messages from the same user.
_session_locks: dict[str, asyncio.Lock] = {}
# Deduplication ring buffer: bounded to avoid unbounded memory growth.
_seen_message_ids: deque[str] = deque(maxlen=2000)
_seen_message_ids_set: set[str] = set()


def _session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


def _is_duplicate(message_id: str) -> bool:
    if message_id in _seen_message_ids_set:
        return True
    # Evict oldest entry when buffer is full
    if len(_seen_message_ids) == _seen_message_ids.maxlen:
        _seen_message_ids_set.discard(_seen_message_ids[0])
    _seen_message_ids.append(message_id)
    _seen_message_ids_set.add(message_id)
    return False


@router.get("/api/channels/whatsapp/meta/webhook", response_class=PlainTextResponse)
@router.get("/webhooks/whatsapp/meta", response_class=PlainTextResponse)
async def verify_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    if not WHATSAPP_META_VERIFY_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WHATSAPP_META_VERIFY_TOKEN is not configured",
        )

    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hub.mode",
        )

    if not verify_meta_webhook_token(hub_verify_token, WHATSAPP_META_VERIFY_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verify token",
        )

    return hub_challenge


async def _handle_inbound(inbound, agent_service: AgentService, adapter) -> None:
    """Process one inbound message, serialized per session via lock."""
    phone_number_id = inbound.phone_number_id or WHATSAPP_META_PHONE_NUMBER_ID
    if not phone_number_id:
        logger.error("whatsapp_meta missing phone_number_id message_id=%s", inbound.message_id)
        return

    # Transcribe audio message before building the request
    if inbound.audio_id:
        if not DEEPGRAM_API_KEY:
            logger.warning("whatsapp_meta audio received but DEEPGRAM_API_KEY not set, skipping")
            return
        try:
            audio_bytes = await download_media(
                api_version=WHATSAPP_META_API_VERSION,
                media_id=inbound.audio_id,
                access_token=WHATSAPP_META_ACCESS_TOKEN,
            )
            transcript = await deepgram_transcribe(
                audio_bytes,
                DEEPGRAM_API_KEY,
                language=DEEPGRAM_STT_LANGUAGE,
                model=DEEPGRAM_STT_MODEL,
                content_type="audio/ogg",
            )
            if not transcript:
                logger.info("whatsapp_meta audio transcription empty, skipping")
                return
            logger.info("whatsapp_meta audio transcript=%r from=%s", transcript[:80], inbound.from_number)
            from dataclasses import replace
            inbound = replace(inbound, text=transcript)
        except Exception:
            logger.exception("whatsapp_meta audio transcription failed message_id=%s", inbound.message_id)
            return

    assist_request = adapter.to_assist_request(
        inbound,
        prompt_name=WHATSAPP_META_PROMPT_NAME,
        model_name=WHATSAPP_META_MODEL_NAME,
        temperature=WHATSAPP_META_TEMPERATURE,
    )
    session_id = assist_request.sessionId or inbound.from_number

    # Track conversation for follow-up scheduling
    is_new = await upsert_conversation(thread_id=session_id, phone_number=inbound.from_number)

    if is_new and WHATSAPP_NOTIFY_TO and WHATSAPP_META_ACCESS_TOKEN and WHATSAPP_META_PHONE_NUMBER_ID:
        try:
            await send_meta_text_message(
                api_version=WHATSAPP_META_API_VERSION,
                phone_number_id=phone_number_id,
                access_token=WHATSAPP_META_ACCESS_TOKEN,
                to=WHATSAPP_NOTIFY_TO,
                text=f"👋 Nueva conversación iniciada\n📱 Número: {inbound.from_number}",
            )
            logger.info("new_conversation notification sent for %s", inbound.from_number)
        except Exception:
            logger.exception("new_conversation notification failed for %s", inbound.from_number)

    lock = _session_lock(session_id)
    async with lock:
        try:
            logger.info(
                "whatsapp_meta processing message_id=%s from=%s session=%s",
                inbound.message_id, inbound.from_number, session_id,
            )
            if inbound.message_id:
                await send_typing_action(
                    api_version=WHATSAPP_META_API_VERSION,
                    phone_number_id=phone_number_id,
                    access_token=WHATSAPP_META_ACCESS_TOKEN,
                    message_id=inbound.message_id,
                )

            assist_response = await process_request(assist_request, agent_service)
            answer_text = adapter.extract_outbound_text(assist_response)
            if not answer_text:
                answer_text = "Gracias por tu mensaje. En breve te ayudamos."

            await send_meta_text_message(
                api_version=WHATSAPP_META_API_VERSION,
                phone_number_id=phone_number_id,
                access_token=WHATSAPP_META_ACCESS_TOKEN,
                to=inbound.from_number,
                text=answer_text,
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "whatsapp_meta_processing_error message_id=%s session=%s",
                inbound.message_id, session_id,
            )


@router.post("/api/channels/whatsapp/meta/webhook")
@router.post("/webhooks/whatsapp/meta")
async def receive_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    agent_service: AgentService = Depends(get_agent_service),
):
    if not WHATSAPP_META_ACCESS_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WHATSAPP_META_ACCESS_TOKEN is not configured",
        )

    raw_payload = await request.body()

    if WHATSAPP_META_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not validate_meta_signature(raw_payload, signature, WHATSAPP_META_APP_SECRET):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    try:
        payload = json.loads(raw_payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    try:
        adapter = get_whatsapp_adapter(WHATSAPP_PROVIDER)
    except AdapterNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    inbound_messages = adapter.extract_inbound_messages(payload)

    if not inbound_messages:
        return {"status": "ignored"}

    queued = 0
    for inbound in inbound_messages:
        # Deduplicate: Meta retries webhooks on timeout
        if inbound.message_id and _is_duplicate(inbound.message_id):
            logger.info("whatsapp_meta duplicate message_id=%s skipped", inbound.message_id)
            continue

        # Schedule background processing — returns 200 to Meta immediately
        background_tasks.add_task(_handle_inbound, inbound, agent_service, adapter)
        queued += 1

    return {"status": "ok", "queued": queued}
