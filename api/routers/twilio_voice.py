"""Twilio Voice webhook router — Deepgram STT + TTS edition.

Flow per call turn:
  1. /webhooks/voice/incoming  → <Say> greeting + <Record action=/webhooks/voice/transcribe>
  2. /webhooks/voice/transcribe → download recording → Deepgram STT → agent
                                → Deepgram TTS → /audio/{key} → <Play> + <Record>
  3. /audio/{key}              → serve temporary MP3 bytes to Twilio's <Play>
"""

from __future__ import annotations

import logging
import re
import time

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
# HTTPException is kept for the /audio/{key} 404 — all voice webhook handlers
# must return TwiML instead of raising exceptions.
from fastapi.responses import Response

from api.agent_service import AgentService
from api.dependencies import get_agent_service
from api.handlers import process_request
from infra.twilio_voice import audio_store
from infra.twilio_voice.adapter import TwilioVoiceAdapter, TwilioVoiceCall
from infra.twilio_voice.deepgram_client import synthesize, transcribe
from infra.twilio_voice.twiml import (
    hangup_response,
    play_and_record,
    record_response,
    transfer_response,
)
from infra.twilio_voice.webhook import validate_twilio_signature
from settings import (
    DEEPGRAM_API_KEY,
    DEEPGRAM_STT_LANGUAGE,
    DEEPGRAM_STT_MODEL,
    DEEPGRAM_TTS_MODEL,
    TWILIO_ACCOUNT_SID,
    TWILIO_VOICE_AUTH_TOKEN,
    TWILIO_VOICE_BASE_URL,
    TWILIO_VOICE_GREETING,
    TWILIO_VOICE_HANDOFF_NUMBER,
    TWILIO_VOICE_MODEL_NAME,
    TWILIO_VOICE_PROMPT_NAME,
    TWILIO_VOICE_TEMPERATURE,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_TWIML = "application/xml"
_TRANSCRIBE_PATH = "/webhooks/voice/transcribe"
_AUDIO_PATH = "/audio"

_HANDOFF_TRIGGERS = ("transferir", "agente humano", "hablar con una persona", "escalar")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _twiml(content: str) -> Response:
    return Response(content=content, media_type=_TWIML)


def _base_url(request: Request) -> str:
    if TWILIO_VOICE_BASE_URL:
        return TWILIO_VOICE_BASE_URL.rstrip("/")
    url = request.url
    return f"{url.scheme}://{url.netloc}"


def _transcribe_url(request: Request) -> str:
    return _base_url(request) + _TRANSCRIBE_PATH


def _audio_url(request: Request, key: str) -> str:
    return f"{_base_url(request)}{_AUDIO_PATH}/{key}"


def _needs_handoff(text: str) -> bool:
    lowered = text.lower()
    return any(trigger in lowered for trigger in _HANDOFF_TRIGGERS)


def _check_signature(request: Request, form_data: dict[str, str]) -> bool:
    """
    Returns False if the Twilio signature is invalid.
    Never raises — callers must always return TwiML, not JSON errors.
    """
    if not TWILIO_VOICE_AUTH_TOKEN:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    base = TWILIO_VOICE_BASE_URL.rstrip("/") if TWILIO_VOICE_BASE_URL else f"{request.url.scheme}://{request.url.netloc}"
    canonical_url = base + str(request.url.path)
    if request.url.query:
        canonical_url += "?" + request.url.query
    valid = validate_twilio_signature(TWILIO_VOICE_AUTH_TOKEN, canonical_url, form_data, signature)
    if not valid:
        logger.warning("twilio_voice_invalid_signature url=%s", canonical_url)
    return valid


async def _download_recording(recording_url: str) -> bytes:
    """Download a Twilio recording as MP3, authenticating with Basic auth."""
    # Twilio requires the .mp3 suffix to return the right format
    url = recording_url if recording_url.endswith(".mp3") else recording_url + ".mp3"
    auth = (TWILIO_ACCOUNT_SID, TWILIO_VOICE_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, auth=auth, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


def _clean_for_voice(text: str) -> str:
    """Strip markdown and limit to 2 sentences — long text kills TTS latency."""
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n+", " ", text)
    text = text.strip()
    # Truncate to first 2 sentences to keep TTS under ~1s
    sentences = re.split(r"(?<=[.!?¿¡])\s+", text)
    return " ".join(sentences[:2]).strip()


async def _tts(text: str) -> bytes:
    return await synthesize(_clean_for_voice(text), DEEPGRAM_API_KEY, model=DEEPGRAM_TTS_MODEL)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/webhooks/voice/incoming")
async def voice_incoming(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
):
    """Called by Twilio when an inbound call starts. Returns greeting + first Record."""
    try:
        form_data = {k: str(v) for k, v in (await request.form()).items()}
        if not _check_signature(request, form_data):
            return _twiml(hangup_response(""))

        logger.info("voice_incoming call_sid=%s from=%s to=%s", CallSid, From, To)

        transcribe_url = _transcribe_url(request)

        if DEEPGRAM_API_KEY:
            tts_bytes = await _tts(TWILIO_VOICE_GREETING)
            key = audio_store.put(tts_bytes)
            return _twiml(play_and_record(_audio_url(request, key), transcribe_url))

        return _twiml(record_response(TWILIO_VOICE_GREETING, transcribe_url))

    except Exception:  # pylint: disable=broad-except
        logger.exception("voice_incoming_error call_sid=%s", CallSid)
        return _twiml(record_response(TWILIO_VOICE_GREETING, _transcribe_url(request)))


@router.post("/webhooks/voice/transcribe")
async def voice_transcribe(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
    RecordingUrl: str = Form(default=""),
    RecordingDuration: str = Form(default="0"),
    CallStatus: str = Form(default="in-progress"),
    agent_service: AgentService = Depends(get_agent_service),
):
    """
    Called by Twilio after <Record> finishes.
    Runs the full pipeline: download → STT → agent → TTS → Play + Record.
    Always returns TwiML — never JSON — so Twilio never sees an "application error".
    """
    transcribe_url = _transcribe_url(request)

    try:
        form_data = {k: str(v) for k, v in (await request.form()).items()}
        if not _check_signature(request, form_data):
            return _twiml(hangup_response(""))

        logger.info(
            "voice_transcribe call_sid=%s from=%s duration=%s status=%s",
            CallSid, From, RecordingDuration, CallStatus,
        )

        if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
            return _twiml(hangup_response(""))

        if not RecordingUrl:
            logger.warning("voice_transcribe missing RecordingUrl call_sid=%s", CallSid)
            return _twiml(record_response("No te escuché bien, ¿me repites?", transcribe_url))

        if int(RecordingDuration or 0) < 1:
            return _twiml(record_response("No te escuché bien, ¿me repites?", transcribe_url))

        t0 = time.perf_counter()

        # 1) Download recording from Twilio
        audio_bytes = await _download_recording(RecordingUrl)
        t1 = time.perf_counter()
        logger.info("voice_transcribe step=download bytes=%d t=%.2fs call_sid=%s", len(audio_bytes), t1 - t0, CallSid)

        # 2) Deepgram STT: audio → text
        if not DEEPGRAM_API_KEY:
            raise RuntimeError("DEEPGRAM_KEY not configured")

        transcript = await transcribe(
            audio_bytes,
            DEEPGRAM_API_KEY,
            language=DEEPGRAM_STT_LANGUAGE,
            model=DEEPGRAM_STT_MODEL,
        )
        t2 = time.perf_counter()
        logger.info("voice_transcribe step=stt stt=%r t=%.2fs call_sid=%s", transcript[:80], t2 - t1, CallSid)

        if not transcript:
            return _twiml(record_response("No te entendí bien, ¿puedes repetirlo?", transcribe_url))

        # 3) Agent: text → response text (same path as chat and WhatsApp)
        adapter = TwilioVoiceAdapter()
        call = TwilioVoiceCall(
            call_sid=CallSid,
            from_number=From,
            to_number=To,
            speech_result=transcript,
            call_status=CallStatus,
        )
        assist_request = adapter.to_assist_request(
            call,
            prompt_name=TWILIO_VOICE_PROMPT_NAME,
            model_name=TWILIO_VOICE_MODEL_NAME or None,
            temperature=TWILIO_VOICE_TEMPERATURE,
        )
        assist_response = await process_request(assist_request, agent_service)
        answer_text = adapter.extract_outbound_text(assist_response)
        t3 = time.perf_counter()

        if not answer_text:
            answer_text = "Un momento, ¿puedes repetirme tu consulta?"

        logger.info(
            "voice_transcribe step=agent t=%.2fs response=%r tools=%s call_sid=%s",
            t3 - t2, answer_text[:80], assist_response.tools_used, CallSid,
        )

        # 4) Handoff check
        if _needs_handoff(answer_text) and TWILIO_VOICE_HANDOFF_NUMBER:
            logger.info("voice_handoff call_sid=%s to=%s", CallSid, TWILIO_VOICE_HANDOFF_NUMBER)
            try:
                tts_bytes = await _tts(answer_text)
                key = audio_store.put(tts_bytes)
                return _twiml(
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<Response>"
                    f"<Play>{_audio_url(request, key)}</Play>"
                    f"<Dial>{TWILIO_VOICE_HANDOFF_NUMBER}</Dial>"
                    "</Response>"
                )
            except Exception:  # pylint: disable=broad-except
                return _twiml(transfer_response(TWILIO_VOICE_HANDOFF_NUMBER, message=answer_text))

        # 5) Deepgram TTS: response text → MP3 bytes → serve via /audio/{key}
        tts_bytes = await _tts(answer_text)
        t4 = time.perf_counter()
        logger.info("voice_transcribe step=tts t=%.2fs call_sid=%s", t4 - t3, CallSid)
        key = audio_store.put(tts_bytes)
        return _twiml(play_and_record(_audio_url(request, key), transcribe_url))

    except Exception:  # pylint: disable=broad-except
        logger.exception("voice_transcribe_error call_sid=%s", CallSid)
        return _twiml(hangup_response("Tuve un problema técnico. Por favor llama de nuevo."))


@router.get("/audio/{key}")
async def serve_audio(key: str):
    """Serve a temporary Deepgram TTS clip so Twilio's <Play> can fetch it."""
    data = audio_store.get(key)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found or expired")
    return Response(content=data, media_type="audio/mpeg")
