"""WhatsApp Calling-specific Deepgram wrappers (WebRTC-friendly PCM defaults)."""

from __future__ import annotations

from infra.deepgram.client import synthesize as _synthesize
from infra.deepgram.client import synthesize_stream as _synthesize_stream
from infra.deepgram.client import transcribe as _transcribe


async def transcribe(
    audio_bytes: bytes,
    api_key: str,
    *,
    language: str = "es",
    model: str = "nova-2",
) -> str:
    """
    STT defaults for WhatsApp Calling bridge payloads.

    Assumes PCM16 mono frames when bridging WebRTC audio to bytes.
    """
    return await _transcribe(
        audio_bytes,
        api_key,
        language=language,
        model=model,
        content_type="audio/raw",
        encoding="linear16",
        sample_rate=16000,
        channels=1,
    )


async def synthesize(
    text: str,
    api_key: str,
    *,
    model: str = "aura-2-celeste-es",
) -> bytes:
    """
    TTS defaults for WhatsApp Calling bridge payloads.

    Produces raw PCM16 mono at 16kHz for WebRTC-side conversion/packetization.
    """
    return await _synthesize(
        text,
        api_key,
        model=model,
        encoding="linear16",
        sample_rate=16000,
        container="none",
    )


async def synthesize_stream(
    text: str,
    api_key: str,
    *,
    model: str = "aura-2-celeste-es",
    chunk_size: int = 640,
):
    """
    Stream raw PCM16 mono (16kHz) bytes for WhatsApp Calling/WebRTC bridge.

    chunk_size=640 bytes ~= 20ms at 16kHz linear16 mono.
    """
    async for chunk in _synthesize_stream(
        text,
        api_key,
        model=model,
        encoding="linear16",
        sample_rate=16000,
        container="none",
        chunk_size=chunk_size,
    ):
        yield chunk

