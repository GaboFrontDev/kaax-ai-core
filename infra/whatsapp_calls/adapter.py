"""Adapter helpers for WhatsApp Calling webhook payloads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.models import AgentAssistRequest, AgentAssistResponse


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_number(value: object) -> str:
    if isinstance(value, dict):
        for key in ("phone_number", "wa_id", "id", "number"):
            candidate = _clean(value.get(key))
            if candidate:
                return candidate
        return ""
    return _clean(value)


@dataclass(frozen=True)
class InboundWhatsAppCallEvent:
    call_id: str
    from_number: str
    to_number: str
    event_type: str
    sdp: str | None = None
    sdp_type: str = "offer"
    transcript: str | None = None
    phone_number_id: str | None = None


@dataclass(frozen=True)
class WhatsAppCallTurn:
    call_id: str
    from_number: str
    to_number: str
    transcript: str


@dataclass(frozen=True)
class WhatsAppCallOffer:
    call_id: str
    sdp: str
    sdp_type: str = "offer"


class WhatsAppCallsAdapter:
    channel = "voice"
    provider = "whatsapp-meta-calls"

    def extract_inbound_calls(self, payload: dict[str, Any]) -> list[InboundWhatsAppCallEvent]:
        events: list[InboundWhatsAppCallEvent] = []

        for value in self._iter_value_blocks(payload):
            metadata = value.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}

            phone_number_id = _clean(metadata.get("phone_number_id")) or None
            to_number = _clean(metadata.get("display_phone_number")) or phone_number_id or "unknown"

            call_blocks = value.get("calls")
            if not isinstance(call_blocks, list):
                continue

            for block in call_blocks:
                if not isinstance(block, dict):
                    continue

                call_id = _clean(block.get("id")) or _clean(block.get("call_id")) or _clean(
                    block.get("callId")
                )
                if not call_id:
                    continue

                from_number = (
                    _extract_number(block.get("from"))
                    or _extract_number(block.get("from_number"))
                    or "unknown"
                )
                direct_to = _extract_number(block.get("to")) or _extract_number(block.get("to_number"))
                final_to = direct_to or to_number

                event_type = (
                    _clean(block.get("event"))
                    or _clean(block.get("status"))
                    or _clean(block.get("type"))
                    or "unknown"
                )

                offer = block.get("offer")
                offer = offer if isinstance(offer, dict) else {}
                sdp = (
                    _clean(block.get("sdp"))
                    or _clean(block.get("sdp_offer"))
                    or _clean(offer.get("sdp"))
                    or _clean(offer.get("offer_sdp"))
                ) or None
                sdp_type = _clean(block.get("sdp_type")) or _clean(offer.get("type")) or "offer"

                transcript = (
                    _clean(block.get("transcript"))
                    or _clean(block.get("text"))
                    or _clean(block.get("speech_result"))
                ) or None

                events.append(
                    InboundWhatsAppCallEvent(
                        call_id=call_id,
                        from_number=from_number,
                        to_number=final_to,
                        event_type=event_type,
                        sdp=sdp,
                        sdp_type=sdp_type,
                        transcript=transcript,
                        phone_number_id=phone_number_id,
                    )
                )

        return events

    def to_call_offer(self, event: InboundWhatsAppCallEvent) -> WhatsAppCallOffer | None:
        if not event.sdp:
            return None
        return WhatsAppCallOffer(call_id=event.call_id, sdp=event.sdp, sdp_type=event.sdp_type)

    def to_call_turn(self, event: InboundWhatsAppCallEvent) -> WhatsAppCallTurn | None:
        transcript = _clean(event.transcript)
        if not transcript:
            return None
        return WhatsAppCallTurn(
            call_id=event.call_id,
            from_number=event.from_number,
            to_number=event.to_number,
            transcript=transcript,
        )

    def to_assist_request(
        self,
        turn: WhatsAppCallTurn,
        *,
        prompt_name: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ) -> AgentAssistRequest:
        return AgentAssistRequest(
            userText=turn.transcript,
            requestor=f"wa-call:{turn.from_number}",
            sessionId=f"wa-call:{turn.call_id}",
            streamResponse=False,
            promptName=prompt_name,
            modelName=model_name,
            temperature=temperature,
            excludeTools=["conversation_loop_tool"],
            systemContext=(
                f"CONTEXTO DE LLAMADA:\n"
                f"- Canal: llamada de WhatsApp. Usa channel='whatsapp' al llamar capture_lead_if_ready_tool.\n"
                f"- Número del llamante: {turn.from_number}. Usa caller_phone='{turn.from_number}'.\n"
                f"- El usuario NO puede hacer clic en links durante la llamada.\n"
                f"- Si el usuario pide demo o un link, dile que se lo enviarás por WhatsApp.\n"
                f"- Si el usuario menciona su nombre, pásalo como contact_name al llamar capture_lead_if_ready_tool."
            ),
        )

    def extract_outbound_text(self, response: AgentAssistResponse | dict[str, Any] | str) -> str:
        if isinstance(response, AgentAssistResponse):
            text = response.response
        elif isinstance(response, dict):
            text = str(response.get("response", ""))
        else:
            text = str(response)
        return text.strip()

    def _iter_value_blocks(self, payload: dict[str, Any]):
        if not isinstance(payload, dict):
            return

        # Useful for local tests or simplified payloads.
        root_calls = payload.get("calls")
        if isinstance(root_calls, list):
            yield payload

        entries = payload.get("entry")
        if not isinstance(entries, list):
            return

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            changes = entry.get("changes")
            if not isinstance(changes, list):
                continue
            for change in changes:
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if isinstance(value, dict):
                    yield value
