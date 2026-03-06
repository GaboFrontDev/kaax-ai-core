"""Twilio Voice webhook router — Media Streams + Deepgram live STT + streaming TTS.

Flow:
  1. POST /webhooks/voice/incoming
       → TwiML: <Connect><Stream url="wss://.../ws/voice"/>

  2. WS /ws/voice  (persistent WebSocket for the full call)
       on start   → stream greeting mulaw chunks directly to Twilio
       on media   → audio chunks → Deepgram live STT → final transcript
                  → agent → Deepgram TTS streaming mulaw → Twilio WebSocket
"""

from __future__ import annotations

import asyncio
import base64
import json as _json
import logging
from random import random
import re
import time

from fastapi import APIRouter, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from api.dependencies import get_agent_service_from_cache
from api.handlers import stream_voice_sentences
from infra.twilio_voice.adapter import TwilioVoiceAdapter, TwilioVoiceCall
from infra.twilio_voice.deepgram_live import run_live_transcription
from infra.twilio_voice.deepgram_client import synthesize_stream
from infra.twilio_voice.twiml import (
    hangup_response,
    stream_connect,
    transfer_response,
)
from infra.twilio_voice.twilio_rest import update_call_twiml
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
global _filler_mulaw

_TWIML = "application/xml"
_HANDOFF_TRIGGERS = ("transferir", "agente humano", "hablar con una persona", "escalar")
_FAREWELL_TRIGGERS = ("adiós", "adios", "hasta luego", "hasta pronto", "chao", "chau", "bye", "gracias por todo", "eso es todo", "no necesito más", "no necesito mas")

# Per-call metadata: {call_sid: {"from": str, "to": str}}
# Survives WebSocket reconnections within the same call.
_call_meta: dict[str, dict] = {}

# Filler audio cached as raw mulaw bytes (generated once on first call)
_filler_mulaw: bytes | None = None
_filler_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _twiml(content: str) -> Response:
    return Response(content=content, media_type=_TWIML)


def _ws_url() -> str:
    base = TWILIO_VOICE_BASE_URL.rstrip("/") if TWILIO_VOICE_BASE_URL else ""
    return base.replace("https://", "wss://").replace("http://", "ws://") + "/ws/voice"


def _needs_handoff(text: str) -> bool:
    lowered = text.lower()
    return any(t in lowered for t in _HANDOFF_TRIGGERS)


def _needs_hangup(text: str) -> bool:
    lowered = text.lower()
    return any(t in lowered for t in _FAREWELL_TRIGGERS)


def _check_signature(request: Request, form_data: dict[str, str]) -> bool:
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


def _clean_for_voice(text: str) -> str:
    """Strip markdown and emojis, limit to 2 sentences for TTS."""
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,2}(.+?)_{1,2}", r"\1", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n+", " ", text)
    # Strip emojis (they get read literally or garble TTS)
    text = re.sub(r"[^\x00-\x7F\u00C0-\u024F\u00A1-\u00BF¿¡]", "", text)
    text = text.strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return " ".join(sentences[:2]).strip()


async def _send_mulaw(data: bytes, websocket: WebSocket, stream_sid: str) -> None:
    """Send raw mulaw bytes to Twilio in 320-byte chunks."""
    for i in range(0, len(data), 320):
        await websocket.send_text(_json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(data[i : i + 320]).decode()},
        }))


async def _stream_sentence(text: str, websocket: WebSocket, stream_sid: str) -> None:
    """Stream one TTS sentence directly to Twilio (no clear)."""
    async for chunk in synthesize_stream(text, DEEPGRAM_API_KEY, model=DEEPGRAM_TTS_MODEL):
        await websocket.send_text(_json.dumps({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": base64.b64encode(chunk).decode()},
        }))


async def _clear(websocket: WebSocket, stream_sid: str) -> None:
    await websocket.send_text(_json.dumps({"event": "clear", "streamSid": stream_sid}))

def randomly_select_filler() -> str:
    """Randomly select a filler text from a predefined list.
        Avoid repetition and keep the conversation engaging for the user while waiting for the agent's response.
        
    """
    fillers = [
        "Ok",
        "Vale",
        "Ah, entiendo",
        "Listo",
        "Gracias",
    ]
    new = random.choice(fillers)
    while new == _filler_mulaw:
        new = randomly_select_filler()  # Avoid repeating the same filler
    _filler_mulaw = new
    return new

async def _get_filler_audio() -> bytes | None:
    """Return cached mulaw filler audio, generating it once on first call."""
    global _filler_mulaw
    if _filler_mulaw is not None:
        return _filler_mulaw
    if not DEEPGRAM_API_KEY:
        return None
    async with _filler_lock:
        if _filler_mulaw is not None:
            return _filler_mulaw
        try:
            chunks: list[bytes] = []
            async for chunk in synthesize_stream(randomly_select_filler(), DEEPGRAM_API_KEY, model=DEEPGRAM_TTS_MODEL):
                chunks.append(chunk)
            _filler_mulaw = b"".join(chunks)
            logger.info("voice_filler cached %d bytes", len(_filler_mulaw))
        except Exception:  # pylint: disable=broad-except
            logger.error("voice_filler generation error", exc_info=True)
            logger.warning("voice_filler generation failed")
    return _filler_mulaw


# ---------------------------------------------------------------------------
# Incoming call webhook
# ---------------------------------------------------------------------------

@router.post("/webhooks/voice/incoming")
async def voice_incoming(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(...),
    To: str = Form(...),
):
    """Called by Twilio when a call arrives. Opens a Media Stream WebSocket."""
    try:
        form_data = {k: str(v) for k, v in (await request.form()).items()}
        if not _check_signature(request, form_data):
            return _twiml(hangup_response(""))

        logger.info("voice_incoming call_sid=%s from=%s to=%s", CallSid, From, To)

        # Store call metadata so the WebSocket handler can build AgentAssistRequest
        _call_meta[CallSid] = {"from": From, "to": To}

        # Open the Media Stream WebSocket — greeting is streamed directly from there
        return _twiml(stream_connect(_ws_url()))

    except Exception:  # pylint: disable=broad-except
        logger.exception("voice_incoming_error call_sid=%s", CallSid)
        return _twiml(hangup_response(""))


# ---------------------------------------------------------------------------
# Media Streams WebSocket
# ---------------------------------------------------------------------------

@router.websocket("/ws/voice")
async def voice_stream(websocket: WebSocket):
    """
    Persistent WebSocket that handles the full conversation loop:
    audio in → Deepgram STT → agent → Deepgram TTS → Twilio REST update.

    No HTTP timeout applies here — the connection stays open for the whole call.
    """
    await websocket.accept()

    call_sid: str | None = None
    stream_sid: str | None = None
    audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    # Lock prevents a second agent call while the first is still running
    agent_busy = asyncio.Lock()
    deepgram_task: asyncio.Task | None = None

    async def handle_transcript(transcript: str) -> None:
        """Called by Deepgram on each final transcript."""
        if agent_busy.locked():
            logger.debug("voice_stream agent busy, dropping transcript=%r", transcript[:40])
            return

        async with agent_busy:
            t0 = time.perf_counter()
            meta = _call_meta.get(call_sid, {})
            logger.info("voice_stream transcript=%r call_sid=%s", transcript[:80], call_sid)

            try:
                agent_svc = get_agent_service_from_cache()
                adapter = TwilioVoiceAdapter()
                call = TwilioVoiceCall(
                    call_sid=call_sid,
                    from_number=meta.get("from", ""),
                    to_number=meta.get("to", ""),
                    speech_result=transcript,
                )
                assist_request = adapter.to_assist_request(
                    call,
                    prompt_name=TWILIO_VOICE_PROMPT_NAME,
                    model_name=TWILIO_VOICE_MODEL_NAME or None,
                    temperature=TWILIO_VOICE_TEMPERATURE,
                )

                # 1. Send filler immediately so user hears something while LLM thinks
                filler = await _get_filler_audio()
                if filler:
                    await _send_mulaw(filler, websocket, stream_sid)

                # 2. Stream agent sentences → TTS concurrently
                sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
                collected: list[str] = []

                async def _collect() -> None:
                    try:
                        async for sentence in stream_voice_sentences(assist_request, agent_svc):
                            await sentence_queue.put(sentence)
                    except Exception:  # pylint: disable=broad-except
                        logger.exception("voice_stream collect error call_sid=%s", call_sid)
                    finally:
                        await sentence_queue.put(None)

                async def _play() -> None:
                    first = True
                    while True:
                        sentence = await sentence_queue.get()
                        if sentence is None:
                            break
                        clean = _clean_for_voice(sentence)
                        if not clean:
                            continue
                        collected.append(clean)
                        if first:
                            # Clear filler before first real audio
                            await _clear(websocket, stream_sid)
                            logger.info(
                                "voice_stream first_audio t=%.2fs sentence=%r call_sid=%s",
                                time.perf_counter() - t0, clean[:60], call_sid,
                            )
                            first = False
                        await _stream_sentence(clean, websocket, stream_sid)

                await asyncio.gather(_collect(), _play())

                full_response = " ".join(collected)
                logger.info(
                    "voice_stream step=total t=%.2fs response=%r call_sid=%s",
                    time.perf_counter() - t0, full_response[:80], call_sid,
                )

                if not full_response:
                    await _stream_sentence("Un momento, ¿puedes repetirme tu consulta?", websocket, stream_sid)
                    return

                # Handoff
                if _needs_handoff(full_response) and TWILIO_VOICE_HANDOFF_NUMBER:
                    logger.info("voice_stream handoff call_sid=%s", call_sid)
                    twiml = transfer_response(TWILIO_VOICE_HANDOFF_NUMBER)
                    await update_call_twiml(TWILIO_ACCOUNT_SID, TWILIO_VOICE_AUTH_TOKEN, call_sid, twiml)
                    return

                # Hangup
                if _needs_hangup(transcript) or _needs_hangup(full_response):
                    logger.info("voice_stream hangup call_sid=%s", call_sid)
                    twiml = hangup_response("")
                    await update_call_twiml(TWILIO_ACCOUNT_SID, TWILIO_VOICE_AUTH_TOKEN, call_sid, twiml)
                    _call_meta.pop(call_sid, None)

            except Exception:  # pylint: disable=broad-except
                logger.exception("voice_stream handle_transcript error call_sid=%s", call_sid)

    try:
        async for raw in websocket.iter_text():
            data = _json.loads(raw)
            event = data.get("event")

            if event == "connected":
                logger.info("voice_stream ws_connected")

            elif event == "start":
                call_sid = data["start"]["callSid"]
                stream_sid = data["start"]["streamSid"]
                logger.info("voice_stream stream_start call_sid=%s stream_sid=%s", call_sid, stream_sid)

                deepgram_task = asyncio.create_task(
                    run_live_transcription(
                        DEEPGRAM_API_KEY,
                        audio_queue,
                        handle_transcript,
                        language=DEEPGRAM_STT_LANGUAGE,
                        model=DEEPGRAM_STT_MODEL,
                    )
                )

                # Pre-warm filler audio cache
                asyncio.ensure_future(_get_filler_audio())

                # Stream greeting directly to caller
                if TWILIO_VOICE_GREETING and DEEPGRAM_API_KEY:
                    asyncio.ensure_future(_stream_sentence(
                        _clean_for_voice(TWILIO_VOICE_GREETING), websocket, stream_sid
                    ))

            elif event == "media":
                chunk = base64.b64decode(data["media"]["payload"])
                try:
                    audio_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass  # Drop chunk if Deepgram is lagging

            elif event == "stop":
                logger.info("voice_stream stream_stop call_sid=%s", call_sid)
                await audio_queue.put(None)
                break

    except WebSocketDisconnect:
        logger.info("voice_stream ws_disconnected call_sid=%s", call_sid)
    except Exception:
        logger.exception("voice_stream error call_sid=%s", call_sid)
    finally:
        await audio_queue.put(None)
        if deepgram_task and not deepgram_task.done():
            deepgram_task.cancel()
        # Don't pop _call_meta here — call may reconnect (after TTS play)


