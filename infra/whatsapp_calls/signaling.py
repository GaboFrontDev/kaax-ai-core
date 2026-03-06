"""WebRTC signaling helpers for WhatsApp Calling."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import time
from typing import Any

from infra.whatsapp_calls.adapter import WhatsAppCallOffer

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency at runtime
    from aiortc import RTCPeerConnection, RTCSessionDescription
except Exception as exc:  # pragma: no cover - optional dependency at runtime
    RTCPeerConnection = None  # type: ignore[assignment]
    RTCSessionDescription = None  # type: ignore[assignment]
    _AIORTC_IMPORT_ERROR = exc
else:
    _AIORTC_IMPORT_ERROR = None


@dataclass(frozen=True)
class WhatsAppCallAnswer:
    call_id: str
    sdp: str
    sdp_type: str = "answer"


class WhatsAppCallSignalingService:
    """Manage WebRTC peer connections for WhatsApp Calling sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._created_at: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def is_available(self) -> bool:
        return RTCPeerConnection is not None and RTCSessionDescription is not None

    def unavailable_reason(self) -> str:
        if self.is_available():
            return ""
        return (
            "aiortc is not installed. Install dependency 'aiortc' to enable "
            "WhatsApp Calling WebRTC SDP negotiation."
        )

    async def create_answer(self, offer: WhatsAppCallOffer) -> WhatsAppCallAnswer:
        if not self.is_available():
            reason = self.unavailable_reason()
            if _AIORTC_IMPORT_ERROR:
                logger.warning("whatsapp_calls_aiortc_unavailable error=%s", _AIORTC_IMPORT_ERROR)
            raise RuntimeError(reason)

        peer_connection = RTCPeerConnection()
        await peer_connection.setRemoteDescription(  # type: ignore[union-attr]
            RTCSessionDescription(sdp=offer.sdp, type=offer.sdp_type)  # type: ignore[operator]
        )
        local_answer = await peer_connection.createAnswer()  # type: ignore[union-attr]
        await peer_connection.setLocalDescription(local_answer)  # type: ignore[union-attr]

        @peer_connection.on("connectionstatechange")
        async def _on_connection_state_change() -> None:
            state = getattr(peer_connection, "connectionState", "unknown")
            if state in {"failed", "closed", "disconnected"}:
                logger.info(
                    "whatsapp_calls_connection_state call_id=%s state=%s",
                    offer.call_id,
                    state,
                )
                await self.close_session(offer.call_id)

        async with self._lock:
            previous = self._sessions.pop(offer.call_id, None)
            self._created_at.pop(offer.call_id, None)
            if previous is not None:
                try:
                    await previous.close()
                except Exception:  # pylint: disable=broad-except
                    logger.exception("whatsapp_calls_previous_session_close_failed call_id=%s", offer.call_id)

            self._sessions[offer.call_id] = peer_connection
            self._created_at[offer.call_id] = time()

        local_description = getattr(peer_connection, "localDescription", None)
        if local_description is None or not getattr(local_description, "sdp", ""):
            raise RuntimeError("Failed to produce local SDP answer")

        logger.info("whatsapp_calls_answer_created call_id=%s", offer.call_id)
        return WhatsAppCallAnswer(call_id=offer.call_id, sdp=local_description.sdp, sdp_type="answer")

    async def close_session(self, call_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(call_id, None)
            self._created_at.pop(call_id, None)
        if session is None:
            return
        try:
            await session.close()
        except Exception:  # pylint: disable=broad-except
            logger.exception("whatsapp_calls_session_close_failed call_id=%s", call_id)

    async def close_all(self) -> None:
        async with self._lock:
            items = list(self._sessions.items())
            self._sessions.clear()
            self._created_at.clear()
        for call_id, session in items:
            try:
                await session.close()
            except Exception:  # pylint: disable=broad-except
                logger.exception("whatsapp_calls_session_close_failed call_id=%s", call_id)

