"""WhatsApp Meta webhook router."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from api.agent_service import AgentService
from api.dependencies import get_agent_service
from api.handlers import process_request
from infra.whatsapp_meta.adapter import WhatsAppMetaAdapter
from infra.whatsapp_meta.client import send_meta_text_message, send_typing_action
from infra.whatsapp_meta.webhook import (
    validate_meta_signature,
    verify_meta_webhook_token,
)
from settings import (
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_APP_SECRET,
    WHATSAPP_META_MODEL_NAME,
    WHATSAPP_META_PHONE_NUMBER_ID,
    WHATSAPP_META_PROMPT_NAME,
    WHATSAPP_META_TEMPERATURE,
    WHATSAPP_META_VERIFY_TOKEN,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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


@router.post("/api/channels/whatsapp/meta/webhook")
@router.post("/webhooks/whatsapp/meta")
async def receive_webhook(
    request: Request,
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

    adapter = WhatsAppMetaAdapter()
    inbound_messages = adapter.extract_inbound_messages(payload)

    if not inbound_messages:
        return {"status": "ignored", "processed": 0, "errors": []}

    processed = 0
    errors: list[dict[str, Any]] = []

    for inbound in inbound_messages:
        try:
            phone_number_id = inbound.phone_number_id or WHATSAPP_META_PHONE_NUMBER_ID
            if not phone_number_id:
                errors.append(
                    {
                        "message_id": inbound.message_id,
                        "error": "Missing phone_number_id in payload and settings",
                    }
                )
                continue

            if inbound.message_id:
                await send_typing_action(
                    api_version=WHATSAPP_META_API_VERSION,
                    phone_number_id=phone_number_id,
                    access_token=WHATSAPP_META_ACCESS_TOKEN,
                    message_id=inbound.message_id,
                )

            assist_request = adapter.to_assist_request(
                inbound,
                prompt_name=WHATSAPP_META_PROMPT_NAME,
                model_name=WHATSAPP_META_MODEL_NAME,
                temperature=WHATSAPP_META_TEMPERATURE,
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
            processed += 1
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("whatsapp_meta_processing_error")
            errors.append({"message_id": inbound.message_id, "error": str(exc)})

    return {
        "status": "ok",
        "received": len(inbound_messages),
        "processed": processed,
        "errors": errors,
    }
