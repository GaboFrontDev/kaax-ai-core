"""Registry to resolve channel adapters by channel/provider."""

from __future__ import annotations

from typing import Any, Protocol, cast

from api.models import AgentAssistRequest, AgentAssistResponse
from infra.twilio_voice.adapter import TwilioVoiceAdapter
from infra.whatsapp_meta.adapter import WhatsAppMetaAdapter


class AdapterNotConfiguredError(ValueError):
    """Raised when a channel/provider pair has no registered adapter."""


class ChannelAdapter(Protocol):
    channel: str
    provider: str

    def to_assist_request(
        self,
        inbound: Any,
        *,
        prompt_name: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ) -> AgentAssistRequest: ...

    def extract_outbound_text(
        self,
        response: AgentAssistResponse | dict[str, Any] | str,
    ) -> str: ...


class WhatsAppAdapter(ChannelAdapter, Protocol):
    def extract_inbound_messages(self, payload: dict[str, Any]) -> list[Any]: ...


class VoiceAdapter(ChannelAdapter, Protocol):
    """Voice adapters use the common to_assist_request/extract_outbound_text contract."""


_ADAPTERS: dict[tuple[str, str], ChannelAdapter] = {}


def _normalize_key(channel: str, provider: str) -> tuple[str, str]:
    normalized_channel = channel.strip().lower()
    normalized_provider = provider.strip().lower()
    if not normalized_channel:
        raise AdapterNotConfiguredError("Adapter channel cannot be empty")
    if not normalized_provider:
        raise AdapterNotConfiguredError("Adapter provider cannot be empty")
    return normalized_channel, normalized_provider


def register_channel_adapter(
    *,
    channel: str,
    provider: str,
    adapter: ChannelAdapter,
) -> None:
    _ADAPTERS[_normalize_key(channel, provider)] = adapter


def get_channel_adapter(*, channel: str, provider: str) -> ChannelAdapter:
    key = _normalize_key(channel, provider)
    adapter = _ADAPTERS.get(key)
    if adapter is None:
        available = ", ".join(
            f"{known_channel}:{known_provider}"
            for known_channel, known_provider in sorted(_ADAPTERS.keys())
        ) or "none"
        raise AdapterNotConfiguredError(
            f"No adapter registered for {key[0]}:{key[1]}. Available: {available}"
        )
    return adapter


def get_whatsapp_adapter(provider: str) -> WhatsAppAdapter:
    adapter = get_channel_adapter(channel="whatsapp", provider=provider)
    if not hasattr(adapter, "extract_inbound_messages"):
        raise AdapterNotConfiguredError(
            f"Adapter whatsapp:{provider.strip().lower()} does not support inbound message extraction"
        )
    return cast(WhatsAppAdapter, adapter)


def get_voice_adapter(provider: str) -> VoiceAdapter:
    return cast(VoiceAdapter, get_channel_adapter(channel="voice", provider=provider))


def list_channel_adapters() -> list[tuple[str, str]]:
    return sorted(_ADAPTERS.keys())


register_channel_adapter(
    channel="whatsapp",
    provider="meta",
    adapter=WhatsAppMetaAdapter(),
)
register_channel_adapter(
    channel="voice",
    provider="twilio",
    adapter=TwilioVoiceAdapter(),
)
