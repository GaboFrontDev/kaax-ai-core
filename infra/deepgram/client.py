"""Shared Deepgram STT/TTS client helpers."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_STT_URL = "https://api.deepgram.com/v1/listen"
_TTS_URL = "https://api.deepgram.com/v1/speak"
_TIMEOUT = 30.0


def _to_bool_param(value: bool) -> str:
    return "true" if value else "false"


def _build_stt_params(
    *,
    model: str,
    language: str,
    smart_format: bool,
    punctuate: bool,
    encoding: str | None,
    sample_rate: int | None,
    channels: int | None,
    extra_params: dict[str, str] | None,
) -> dict[str, str]:
    params: dict[str, str] = {
        "model": model,
        "language": language,
        "smart_format": _to_bool_param(smart_format),
        "punctuate": _to_bool_param(punctuate),
    }
    if encoding:
        params["encoding"] = encoding
    if sample_rate:
        params["sample_rate"] = str(sample_rate)
    if channels:
        params["channels"] = str(channels)
    if extra_params:
        params.update(extra_params)
    return params


def _build_tts_params(
    *,
    model: str,
    encoding: str | None,
    sample_rate: int | None,
    container: str | None,
    extra_params: dict[str, str] | None,
) -> dict[str, str]:
    params: dict[str, str] = {"model": model}
    if encoding:
        params["encoding"] = encoding
    if sample_rate:
        params["sample_rate"] = str(sample_rate)
    if container:
        params["container"] = container
    if extra_params:
        params.update(extra_params)
    return params


async def transcribe(
    audio_bytes: bytes,
    api_key: str,
    *,
    language: str = "es",
    model: str = "nova-2",
    content_type: str = "audio/mpeg",
    smart_format: bool = True,
    punctuate: bool = True,
    encoding: str | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Send audio bytes to Deepgram STT, return transcript text."""
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }
    params = _build_stt_params(
        model=model,
        language=language,
        smart_format=smart_format,
        punctuate=punctuate,
        encoding=encoding,
        sample_rate=sample_rate,
        channels=channels,
        extra_params=extra_params,
    )

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(_STT_URL, params=params, headers=headers, content=audio_bytes)
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()

    try:
        transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        logger.debug("deepgram_stt transcript=%r", transcript[:80])
        return transcript
    except (KeyError, IndexError, AttributeError):
        logger.warning("deepgram_stt empty result data=%s", data)
        return ""


async def synthesize(
    text: str,
    api_key: str,
    *,
    model: str = "aura-2-celeste-es",
    content_type: str = "text/plain",
    encoding: str | None = None,
    sample_rate: int | None = None,
    container: str | None = None,
    extra_params: dict[str, str] | None = None,
) -> bytes:
    """Send text to Deepgram TTS, return audio bytes."""
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }
    params = _build_tts_params(
        model=model,
        encoding=encoding,
        sample_rate=sample_rate,
        container=container,
        extra_params=extra_params,
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            _TTS_URL,
            params=params,
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
    content_type: str = "text/plain",
    encoding: str | None = None,
    sample_rate: int | None = None,
    container: str | None = None,
    extra_params: dict[str, str] | None = None,
    chunk_size: int = 320,
):
    """Stream Deepgram TTS bytes with channel-specific encoding options."""
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": content_type,
    }
    params = _build_tts_params(
        model=model,
        encoding=encoding,
        sample_rate=sample_rate,
        container=container,
        extra_params=extra_params,
    )
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

