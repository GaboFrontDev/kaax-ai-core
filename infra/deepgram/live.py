"""Shared Deepgram live transcription WebSocket client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlencode

import websockets
import websockets.exceptions

logger = logging.getLogger(__name__)

_WS_URL = "wss://api.deepgram.com/v1/listen"


def build_live_listen_url(
    *,
    model: str,
    language: str,
    encoding: str,
    sample_rate: int,
    smart_format: bool = True,
    punctuate: bool = True,
    endpointing: int = 150,
    channels: int | None = None,
    extra_params: dict[str, str] | None = None,
) -> str:
    params: dict[str, str] = {
        "model": model,
        "language": language,
        "encoding": encoding,
        "sample_rate": str(sample_rate),
        "smart_format": "true" if smart_format else "false",
        "punctuate": "true" if punctuate else "false",
        "endpointing": str(endpointing),
    }
    if channels:
        params["channels"] = str(channels)
    if extra_params:
        params.update(extra_params)
    return f"{_WS_URL}?{urlencode(params)}"


async def run_live_transcription(
    api_key: str,
    audio_queue: asyncio.Queue,
    on_final: Callable[[str], Awaitable[None]],
    *,
    language: str = "es",
    model: str = "nova-2",
    encoding: str = "mulaw",
    sample_rate: int = 8000,
    smart_format: bool = True,
    punctuate: bool = True,
    endpointing: int = 150,
    channels: int | None = None,
    min_confidence: float = 0.7,
    min_words: int = 2,
    extra_params: dict[str, str] | None = None,
) -> None:
    """
    Connect to Deepgram live STT and stream bytes from audio_queue.

    Sentinel value None in audio_queue signals end of stream.
    """
    url = build_live_listen_url(
        model=model,
        language=language,
        encoding=encoding,
        sample_rate=sample_rate,
        smart_format=smart_format,
        punctuate=punctuate,
        endpointing=endpointing,
        channels=channels,
        extra_params=extra_params,
    )
    headers = {"Authorization": f"Token {api_key}"}

    try:
        async with websockets.connect(url, additional_headers=headers) as ws:
            async def _send_audio() -> None:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break
                    try:
                        await ws.send(chunk)
                    except websockets.exceptions.ConnectionClosed:
                        break

            async def _receive_transcripts() -> None:
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        continue

                    if data.get("type") != "Results" or not data.get("is_final"):
                        continue

                    alts = data.get("channel", {}).get("alternatives", [])
                    if not alts:
                        continue

                    transcript = str(alts[0].get("transcript", "")).strip()
                    confidence = float(alts[0].get("confidence", 0.0))
                    if transcript and confidence >= min_confidence and len(transcript.split()) >= min_words:
                        logger.info("deepgram_live final=%r confidence=%.2f", transcript[:80], confidence)
                        await on_final(transcript)

            await asyncio.gather(_send_audio(), _receive_transcripts())

    except websockets.exceptions.ConnectionClosed:
        logger.debug("deepgram_live connection closed normally")
    except Exception:
        logger.exception("deepgram_live error")

