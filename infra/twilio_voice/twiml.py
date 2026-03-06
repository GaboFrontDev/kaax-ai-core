"""Minimal TwiML builders — no external dependency required."""

from __future__ import annotations

import logging
# Alice supports es-MX out of the box, no extra Twilio config needed.
_VOICE = "alice"
_LANGUAGE = "es-MX"

# How many seconds of silence before Gather gives up and falls through.
_TIMEOUT = "8"

logger = logging.getLogger(__name__)

def _esc(text: str) -> str:
    """Escape the four XML special characters that appear in natural Spanish."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _say(text: str) -> str:
    return f'<Say voice="{_VOICE}" language="{_LANGUAGE}">{_esc(text)}</Say>'


def gather_response(agent_text: str, action_url: str) -> str:
    """
    Say agent_text then open a Gather listening for speech.
    If the caller says nothing within _TIMEOUT seconds the Gather falls
    through to the trailing Say+Hangup — avoiding infinite loops.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{_say(agent_text)}"
        f'<Gather input="speech" action="{action_url}" '
        f'language="{_LANGUAGE}" speechTimeout="auto" timeout="{_TIMEOUT}">'
        f"{_say('Adelante.')}"
        "</Gather>"
        # Fallback when caller stays silent after the Gather prompt
        f"{_say('No te escuché. Hasta pronto.')}"
        "<Hangup/>"
        "</Response>"
    )


def hangup_response(farewell_text: str) -> str:
    """Say a farewell phrase then hang up."""
    logger.info("No speech detected. Sending farewell and hanging up.")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{_say(farewell_text)}"
        "<Hangup/>"
        "</Response>"
    )


def record_response(prompt_text: str, action_url: str) -> str:
    """
    Say prompt_text then record the caller's response.
    If timeout fires with no speech, falls through to Say+Hangup.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{_say(prompt_text)}"
        f'<Record action="{action_url}" maxLength="30" playBeep="false" timeout="5"/>'
        # Fallback: caller said nothing
        f"{_say('No te escuché. Hasta pronto.')}"
        "<Hangup/>"
        "</Response>"
    )


def play_and_record(audio_url: str, action_url: str) -> str:
    """
    Play Deepgram TTS audio then record the caller's response.
    Twilio starts recording immediately after <Play> finishes.
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Play>{audio_url}</Play>"
        f'<Record action="{action_url}" maxLength="30" playBeep="false" timeout="5"/>'
        f"{_say('No te escuché. Hasta pronto.')}"
        "<Hangup/>"
        "</Response>"
    )


def stream_connect(ws_url: str, greeting: str = "") -> str:
    """Connect call to a Media Streams WebSocket, optionally playing a greeting first."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    if greeting:
        parts.append(_say(greeting))
    parts.append(f'<Connect><Stream url="{ws_url}"/></Connect>')
    parts.append("</Response>")
    return "".join(parts)


def stream_play_then_connect(audio_url: str, ws_url: str) -> str:
    """Play TTS audio then reconnect to Media Stream for the next turn."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"<Play>{audio_url}</Play>"
        f'<Connect><Stream url="{ws_url}"/></Connect>'
        "</Response>"
    )


def transfer_response(phone_number: str, message: str = "") -> str:
    """Optionally say a message then dial a human-agent number."""
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', "<Response>"]
    if message:
        parts.append(_say(message))
    parts.append(f"<Dial>{_esc(phone_number)}</Dial>")
    parts.append("</Response>")
    return "".join(parts)
