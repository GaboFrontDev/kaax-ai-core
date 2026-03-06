"""In-memory temporary audio store for serving TTS clips to Twilio's <Play>."""

from __future__ import annotations

import asyncio
import uuid

# {uuid_key: mp3_bytes}
_store: dict[str, bytes] = {}

# How long to keep audio before evicting (seconds). Plenty for any call turn.
_TTL = 300


def put(audio_bytes: bytes) -> str:
    """Store audio bytes and return the UUID key."""
    key = str(uuid.uuid4())
    _store[key] = audio_bytes
    asyncio.ensure_future(_expire(key))
    return key


def get(key: str) -> bytes | None:
    return _store.get(key)


async def _expire(key: str) -> None:
    await asyncio.sleep(_TTL)
    _store.pop(key, None)
