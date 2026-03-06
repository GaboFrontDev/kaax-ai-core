"""Deepgram STT and TTS via REST API — uses httpx (already a project dependency)."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_STT_URL = "https://api.deepgram.com/v1/listen"
_TTS_URL = "https://api.deepgram.com/v1/speak"
_TIMEOUT = 30.0


async def transcribe(
    audio_bytes: bytes,
    api_key: str,
    *,
    language: str = "es",
    model: str = "nova-2",
) -> str:
    """Send audio bytes to Deepgram STT, return transcript text."""
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/mpeg",
    }
    params = {
        "model": model,
        "language": language,
        "smart_format": "true",
        "punctuate": "true",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_STT_URL, params=params, headers=headers, content=audio_bytes)
        resp.raise_for_status()
        data = resp.json()

    try:
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        logger.debug("deepgram_stt transcript=%r", transcript[:80])
        return transcript
    except (KeyError, IndexError):
        logger.warning("deepgram_stt empty result data=%s", data)
        return ""


async def synthesize(
    text: str,
    api_key: str,
    *,
    model: str = "aura-2-celeste-es",
) -> bytes:
    """Send text to Deepgram TTS, return MP3 audio bytes."""
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "text/plain",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TTS_URL,
            params={"model": model},
            headers=headers,
            content=text.encode("utf-8"),
        )
        resp.raise_for_status()
        return resp.content


async def synthesize_stream(
    text: str,
    api_key: str,
    *,
    model: str = "aura-2-celeste-es",
    chunk_size: int = 320,
):
    """
    Stream Deepgram TTS as raw mulaw 8kHz chunks — ready to send directly
    to Twilio Media Streams via WebSocket without any conversion.

    chunk_size=320 bytes = 40ms of mulaw at 8kHz (safe for Twilio).
    """
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "text/plain",
    }
    params = {
        "model": model,
        "encoding": "mulaw",
        "sample_rate": "8000",
        "container": "none",
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        async with client.stream(
            "POST",
            _TTS_URL,
            params=params,
            headers=headers,
            content=text.encode("utf-8"),
        ) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes(chunk_size):
                if chunk:
                    yield chunk
