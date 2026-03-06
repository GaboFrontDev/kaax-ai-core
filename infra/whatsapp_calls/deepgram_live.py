"""WhatsApp Calling-specific Deepgram live STT wrapper."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from infra.deepgram.live import run_live_transcription as _run_live_transcription


async def run_live_transcription(
    api_key: str,
    audio_queue: asyncio.Queue,
    on_final: Callable[[str], Awaitable[None]],
    *,
    language: str = "es",
    model: str = "nova-2",
) -> None:
    """
    WebRTC bridge defaults: linear16 mono @ 16kHz.

    This wrapper is transport-facing only; SDP/WebRTC signaling lives elsewhere.
    """
    await _run_live_transcription(
        api_key,
        audio_queue,
        on_final,
        language=language,
        model=model,
        encoding="linear16",
        sample_rate=16000,
        channels=1,
        endpointing=150,
        min_confidence=0.7,
        min_words=2,
    )

