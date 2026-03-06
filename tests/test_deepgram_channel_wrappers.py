from __future__ import annotations

import asyncio

from infra.whatsapp_calls import deepgram_client as wa_deepgram_client
from infra.whatsapp_calls import deepgram_live as wa_deepgram_live
from infra.twilio_voice import deepgram_client as twilio_deepgram_client
from infra.twilio_voice import deepgram_live as twilio_deepgram_live


def test_twilio_tts_stream_wrapper_uses_mulaw_8k(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_synthesize_stream(text: str, api_key: str, **kwargs):
        captured["text"] = text
        captured["api_key"] = api_key
        captured.update(kwargs)
        yield b"abc"

    monkeypatch.setattr(twilio_deepgram_client, "_synthesize_stream", fake_synthesize_stream)

    async def run() -> None:
        chunks = [
            chunk async for chunk in twilio_deepgram_client.synthesize_stream("hola", "token")
        ]
        assert chunks == [b"abc"]

    asyncio.run(run())

    assert captured["encoding"] == "mulaw"
    assert captured["sample_rate"] == 8000
    assert captured["container"] == "none"
    assert captured["chunk_size"] == 320


def test_whatsapp_tts_stream_wrapper_uses_linear16_16k(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_synthesize_stream(text: str, api_key: str, **kwargs):
        captured["text"] = text
        captured["api_key"] = api_key
        captured.update(kwargs)
        yield b"def"

    monkeypatch.setattr(wa_deepgram_client, "_synthesize_stream", fake_synthesize_stream)

    async def run() -> None:
        chunks = [chunk async for chunk in wa_deepgram_client.synthesize_stream("hola", "token")]
        assert chunks == [b"def"]

    asyncio.run(run())

    assert captured["encoding"] == "linear16"
    assert captured["sample_rate"] == 16000
    assert captured["container"] == "none"
    assert captured["chunk_size"] == 640


def test_twilio_live_stt_wrapper_sets_mulaw(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_live(api_key: str, audio_queue: asyncio.Queue, on_final, **kwargs) -> None:
        captured["api_key"] = api_key
        captured["audio_queue"] = audio_queue
        captured["on_final"] = on_final
        captured.update(kwargs)

    monkeypatch.setattr(twilio_deepgram_live, "_run_live_transcription", fake_run_live)

    async def run() -> None:
        queue: asyncio.Queue = asyncio.Queue()

        async def on_final(_: str) -> None:
            return None

        await twilio_deepgram_live.run_live_transcription("token", queue, on_final)

    asyncio.run(run())

    assert captured["encoding"] == "mulaw"
    assert captured["sample_rate"] == 8000
    assert captured["endpointing"] == 150


def test_whatsapp_live_stt_wrapper_sets_linear16(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_run_live(api_key: str, audio_queue: asyncio.Queue, on_final, **kwargs) -> None:
        captured["api_key"] = api_key
        captured["audio_queue"] = audio_queue
        captured["on_final"] = on_final
        captured.update(kwargs)

    monkeypatch.setattr(wa_deepgram_live, "_run_live_transcription", fake_run_live)

    async def run() -> None:
        queue: asyncio.Queue = asyncio.Queue()

        async def on_final(_: str) -> None:
            return None

        await wa_deepgram_live.run_live_transcription("token", queue, on_final)

    asyncio.run(run())

    assert captured["encoding"] == "linear16"
    assert captured["sample_rate"] == 16000
    assert captured["channels"] == 1
    assert captured["endpointing"] == 150

