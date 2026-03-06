from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.models import AgentAssistResponse
from infra.whatsapp_calls.adapter import (
    WhatsAppCallsAdapter,
    WhatsAppCallOffer,
    WhatsAppCallTurn,
)
from infra.whatsapp_calls.pipeline import WhatsAppCallPipeline
from infra.whatsapp_calls.signaling import WhatsAppCallSignalingService


def test_whatsapp_calls_adapter_extracts_offer_and_turn() -> None:
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {
                                "display_phone_number": "5213322222222",
                                "phone_number_id": "12345",
                            },
                            "calls": [
                                {
                                    "id": "CALL-1",
                                    "from": "5213311111111",
                                    "event": "offer",
                                    "offer": {"type": "offer", "sdp": "v=0..."},
                                    "transcript": "quiero una demo",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }

    adapter = WhatsAppCallsAdapter()
    events = adapter.extract_inbound_calls(payload)
    assert len(events) == 1

    event = events[0]
    assert event.call_id == "CALL-1"
    assert event.from_number == "5213311111111"
    assert event.to_number == "5213322222222"
    assert event.sdp == "v=0..."
    assert event.transcript == "quiero una demo"

    offer = adapter.to_call_offer(event)
    assert isinstance(offer, WhatsAppCallOffer)
    assert offer.call_id == "CALL-1"

    turn = adapter.to_call_turn(event)
    assert isinstance(turn, WhatsAppCallTurn)
    assert turn.transcript == "quiero una demo"


def test_whatsapp_calls_adapter_maps_agent_request_context() -> None:
    adapter = WhatsAppCallsAdapter()
    turn = WhatsAppCallTurn(
        call_id="CALL-99",
        from_number="5213311111111",
        to_number="5213322222222",
        transcript="hola",
    )

    request = adapter.to_assist_request(turn, prompt_name="voice_agent")
    assert request.requestor == "wa-call:5213311111111"
    assert request.sessionId == "wa-call:CALL-99"
    assert request.promptName == "voice_agent"
    assert request.excludeTools == ["conversation_loop_tool"]
    assert "Canal: llamada de WhatsApp" in (request.systemContext or "")


def test_whatsapp_calls_pipeline_without_deepgram(monkeypatch) -> None:
    async def fake_process_request(request, _agent_service):
        assert request.requestor.startswith("wa-call:")
        return AgentAssistResponse(
            response="Te ayudo con eso.",
            tools_used=[],
            completion_time=0.1,
        )

    monkeypatch.setattr("infra.whatsapp_calls.pipeline.process_request", fake_process_request)
    pipeline = WhatsAppCallPipeline(agent_service=SimpleNamespace())
    turn = WhatsAppCallTurn(
        call_id="CALL-2",
        from_number="5213311111111",
        to_number="5213322222222",
        transcript="necesito info",
    )

    async def run() -> None:
        result = await pipeline.handle_turn(turn, deepgram_api_key="")
        assert result.response_text == "Te ayudo con eso."
        assert result.tts_audio == b""

    asyncio.run(run())


def test_whatsapp_calls_signaling_unavailable_raises(monkeypatch) -> None:
    service = WhatsAppCallSignalingService()
    monkeypatch.setattr(service, "is_available", lambda: False)
    monkeypatch.setattr(service, "unavailable_reason", lambda: "aiortc missing")

    async def run() -> None:
        with pytest.raises(RuntimeError, match="aiortc missing"):
            await service.create_answer(
                WhatsAppCallOffer(call_id="CALL-1", sdp="v=0...", sdp_type="offer")
            )

    asyncio.run(run())

