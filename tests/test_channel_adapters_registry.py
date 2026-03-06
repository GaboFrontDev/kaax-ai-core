from __future__ import annotations

import pytest

from api.models import AgentAssistResponse
from infra.adapters import (
    AdapterNotConfiguredError,
    get_voice_adapter,
    get_whatsapp_adapter,
    list_channel_adapters,
)
from infra.twilio_voice.adapter import TwilioVoiceCall
from infra.whatsapp_meta.adapter import InboundWhatsAppMessage


def test_registry_includes_default_channel_provider_pairs() -> None:
    available = list_channel_adapters()

    assert ("voice", "twilio") in available
    assert ("whatsapp", "meta") in available


def test_whatsapp_meta_adapter_request_mapping() -> None:
    adapter = get_whatsapp_adapter("meta")
    inbound = InboundWhatsAppMessage(
        from_number="5213311111111",
        to_number="5213322222222",
        text="Hola",
    )

    request = adapter.to_assist_request(inbound, prompt_name="agent")

    assert request.userText == "Hola"
    assert request.requestor == "wa-meta:5213311111111"
    assert request.sessionId == "wa-meta:5213322222222:5213311111111"
    assert request.promptName == "agent"


def test_twilio_voice_adapter_mapping_and_outbound_normalization() -> None:
    adapter = get_voice_adapter("twilio")
    call = TwilioVoiceCall(
        call_sid="CA123",
        from_number="+5213311111111",
        to_number="+5213322222222",
        speech_result="Necesito una demo",
    )

    request = adapter.to_assist_request(call, model_name="voice-model")
    assert request.requestor == "voice:+5213311111111"
    assert request.sessionId == "voice:CA123"
    assert request.modelName == "voice-model"

    response_model = AgentAssistResponse(
        response=" Listo ",
        tools_used=[],
        completion_time=0.1,
    )
    assert adapter.extract_outbound_text(response_model) == "Listo"
    assert adapter.extract_outbound_text({"response": " Hola "}) == "Hola"
    assert adapter.extract_outbound_text(" Adios ") == "Adios"


def test_unknown_channel_provider_raises() -> None:
    with pytest.raises(AdapterNotConfiguredError):
        get_whatsapp_adapter("twilio")
