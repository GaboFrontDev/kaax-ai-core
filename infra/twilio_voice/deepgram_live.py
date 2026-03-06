"""Deepgram live transcription WebSocket client."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

import websockets
import websockets.exceptions

logger = logging.getLogger(__name__)

_WS_URL = "wss://api.deepgram.com/v1/listen"


async def run_live_transcription(
    api_key: str,
    audio_queue: asyncio.Queue,
    on_final: Callable[[str], Awaitable[None]],
    *,
    language: str = "es",
    model: str = "nova-2",
) -> None:
    """
    Connect to Deepgram live STT, stream audio from audio_queue,
    and call on_final(transcript) for each final result.

    Sentinel value None in audio_queue signals end of stream.
    endpointing=300 → Deepgram marks speech as final after 300ms of silence.
    """
    # Twilio Media Streams sends mulaw-encoded audio at 8000 Hz
    params = (
        f"model={model}&language={language}"
        "&encoding=mulaw&sample_rate=8000"
        "&smart_format=true&punctuate=true&endpointing=150"
    )
    url = f"{_WS_URL}?{params}"
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
                    transcript = alts[0].get("transcript", "").strip()
                    confidence = alts[0].get("confidence", 0.0)
                    # Ignore noise: require at least 2 words and 70% confidence
                    if transcript and confidence >= 0.7 and len(transcript.split()) >= 2:
                        logger.info("deepgram_live final=%r confidence=%.2f", transcript[:80], confidence)
                        await on_final(transcript)

            await asyncio.gather(_send_audio(), _receive_transcripts())

    except websockets.exceptions.ConnectionClosed:
        logger.debug("deepgram_live connection closed normally")
    except Exception:
        logger.exception("deepgram_live error")
