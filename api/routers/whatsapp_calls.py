"""WhatsApp Calling webhook router (events + optional SDP negotiation)."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from api.agent_service import AgentService
from api.dependencies import get_agent_service
from infra.whatsapp_calls.adapter import WhatsAppCallsAdapter
from infra.whatsapp_calls.pipeline import WhatsAppCallPipeline
from infra.whatsapp_calls.signaling import WhatsAppCallSignalingService
from infra.whatsapp_meta.webhook import (
    validate_meta_signature,
    verify_meta_webhook_token,
)
from settings import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_TTS_MODEL,
    WHATSAPP_CALLS_APP_SECRET,
    WHATSAPP_CALLS_INCLUDE_TTS_PAYLOAD,
    WHATSAPP_CALLS_MODEL_NAME,
    WHATSAPP_CALLS_PROMPT_NAME,
    WHATSAPP_CALLS_TEMPERATURE,
    WHATSAPP_CALLS_VERIFY_TOKEN,
)

logger = logging.getLogger(__name__)

router = APIRouter()
_signaling = WhatsAppCallSignalingService()


@router.get("/api/channels/whatsapp/meta/calls", response_class=PlainTextResponse)
@router.get("/calls", response_class=PlainTextResponse)
async def verify_calls_webhook(
    hub_mode: str = Query(default="", alias="hub.mode"),
    hub_verify_token: str = Query(default="", alias="hub.verify_token"),
    hub_challenge: str = Query(default="", alias="hub.challenge"),
):
    if not WHATSAPP_CALLS_VERIFY_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WHATSAPP_CALLS_VERIFY_TOKEN is not configured",
        )

    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid hub.mode",
        )

    if not verify_meta_webhook_token(hub_verify_token, WHATSAPP_CALLS_VERIFY_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid verify token",
        )

    return hub_challenge


@router.post("/api/channels/whatsapp/meta/calls")
@router.post("/calls")
async def receive_calls_webhook(
    request: Request,
    agent_service: AgentService = Depends(get_agent_service),
):
    raw_payload = await request.body()

    if WHATSAPP_CALLS_APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not validate_meta_signature(raw_payload, signature, WHATSAPP_CALLS_APP_SECRET):
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

    adapter = WhatsAppCallsAdapter()
    events = adapter.extract_inbound_calls(payload)
    if not events:
        return {"status": "ignored", "received": 0, "processed": 0, "results": [], "errors": []}

    pipeline = WhatsAppCallPipeline(agent_service)
    processed = 0
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for event in events:
        try:
            event_result: dict[str, Any] = {
                "call_id": event.call_id,
                "event": event.event_type,
                "from": event.from_number,
                "to": event.to_number,
            }

            offer = adapter.to_call_offer(event)
            if offer:
                try:
                    answer = await _signaling.create_answer(offer)
                    event_result["answer"] = {
                        "type": answer.sdp_type,
                        "sdp": answer.sdp,
                    }
                except RuntimeError as exc:
                    event_result["answer"] = {
                        "status": "unavailable",
                        "reason": str(exc),
                    }

            turn = adapter.to_call_turn(event)
            if turn:
                pipeline_result = await pipeline.handle_turn(
                    turn,
                    prompt_name=WHATSAPP_CALLS_PROMPT_NAME,
                    model_name=WHATSAPP_CALLS_MODEL_NAME,
                    temperature=WHATSAPP_CALLS_TEMPERATURE,
                    deepgram_api_key=DEEPGRAM_API_KEY,
                    deepgram_tts_model=DEEPGRAM_TTS_MODEL,
                )
                event_result["agent"] = {
                    "response": pipeline_result.response_text,
                    "tts_audio_bytes": len(pipeline_result.tts_audio),
                    "encoding": "linear16",
                    "sample_rate": 16000,
                }
                if WHATSAPP_CALLS_INCLUDE_TTS_PAYLOAD and pipeline_result.tts_audio:
                    event_result["agent"]["tts_payload_base64"] = base64.b64encode(
                        pipeline_result.tts_audio
                    ).decode("ascii")

            if event.event_type.lower() in {"hangup", "ended", "completed", "terminated"}:
                await _signaling.close_session(event.call_id)
                event_result["session"] = "closed"

            results.append(event_result)
            processed += 1
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("whatsapp_calls_processing_error")
            errors.append({"call_id": event.call_id, "error": str(exc)})

    return {
        "status": "ok",
        "received": len(events),
        "processed": processed,
        "results": results,
        "errors": errors,
    }

