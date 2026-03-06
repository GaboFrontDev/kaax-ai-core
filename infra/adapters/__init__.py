"""Channel adapter registry for provider/channel selection."""

from .registry import (
    AdapterNotConfiguredError,
    ChannelAdapter,
    VoiceAdapter,
    WhatsAppAdapter,
    get_channel_adapter,
    get_voice_adapter,
    get_whatsapp_adapter,
    list_channel_adapters,
    register_channel_adapter,
)

__all__ = [
    "AdapterNotConfiguredError",
    "ChannelAdapter",
    "VoiceAdapter",
    "WhatsAppAdapter",
    "get_channel_adapter",
    "get_voice_adapter",
    "get_whatsapp_adapter",
    "list_channel_adapters",
    "register_channel_adapter",
]
