"""Helpers to normalize WhatsApp Meta payloads into the core API models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from api.models import AgentAssistRequest, AgentAssistResponse


@dataclass(frozen=True)
class InboundWhatsAppMessage:
    from_number: str
    to_number: str
    text: str
    message_id: str | None = None
    phone_number_id: str | None = None


class WhatsAppMetaAdapter:
    def extract_inbound_messages(self, payload: dict[str, Any]) -> list[InboundWhatsAppMessage]:
        messages: list[InboundWhatsAppMessage] = []

        for value in self._iter_value_blocks(payload):
            metadata = value.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}

            phone_number_id = self._clean(metadata.get("phone_number_id"))
            to_number = self._clean(metadata.get("display_phone_number")) or phone_number_id
            if not to_number:
                to_number = "unknown"

            inbound = value.get("messages")
            if not isinstance(inbound, list):
                continue

            for message in inbound:
                if not isinstance(message, dict):
                    continue

                from_number = self._clean(message.get("from"))
                if not from_number:
                    continue

                text = self._extract_text(message)
                if not text:
                    continue

                messages.append(
                    InboundWhatsAppMessage(
                        from_number=from_number,
                        to_number=to_number,
                        text=text,
                        message_id=self._clean(message.get("id")) or None,
                        phone_number_id=phone_number_id or None,
                    )
                )

        return messages

    def to_assist_request(
        self,
        message: InboundWhatsAppMessage,
        *,
        prompt_name: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ) -> AgentAssistRequest:
        return AgentAssistRequest(
            userText=message.text,
            requestor=f"wa-meta:{message.from_number}",
            # Stable memory scope for one user + one business number.
            sessionId=f"wa-meta:{message.to_number}:{message.from_number}",
            streamResponse=False,
            promptName=prompt_name,
            modelName=model_name,
            temperature=temperature,
        )

    def extract_outbound_text(self, response: AgentAssistResponse | dict[str, Any] | str) -> str:
        if isinstance(response, AgentAssistResponse):
            text = response.response
        elif isinstance(response, dict):
            text = str(response.get("response", ""))
        else:
            text = str(response)
        return text.strip()

    async def normalize_inbound(self, raw: dict[str, object]) -> AgentAssistRequest:
        messages = self.extract_inbound_messages(raw)
        if messages:
            return self.to_assist_request(messages[0])

        from_number = self._clean(raw.get("from")) or "unknown"
        to_number = self._clean(raw.get("to")) or "unknown"
        text = self._clean(raw.get("text"))
        return AgentAssistRequest(
            userText=text,
            requestor=f"wa-meta:{from_number}",
            sessionId=f"wa-meta:{to_number}:{from_number}",
            streamResponse=False,
        )

    async def denormalize_outbound(
        self, response: AgentAssistResponse | dict[str, Any] | str
    ) -> dict[str, object]:
        return {"response": self.extract_outbound_text(response)}

    def _iter_value_blocks(self, payload: dict[str, Any]):
        if not isinstance(payload, dict):
            return

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

    def _extract_text(self, message: dict[str, Any]) -> str:
        message_type = self._clean(message.get("type"))

        if message_type == "text":
            text_block = message.get("text")
            if isinstance(text_block, dict):
                return self._clean(text_block.get("body"))
            return ""

        if message_type == "button":
            button = message.get("button")
            if isinstance(button, dict):
                return self._clean(button.get("text"))
            return ""

        if message_type == "interactive":
            interactive = message.get("interactive")
            if not isinstance(interactive, dict):
                return ""

            interactive_type = self._clean(interactive.get("type"))
            if interactive_type == "button_reply":
                button_reply = interactive.get("button_reply")
                if isinstance(button_reply, dict):
                    return self._clean(button_reply.get("title")) or self._clean(
                        button_reply.get("id")
                    )
            if interactive_type == "list_reply":
                list_reply = interactive.get("list_reply")
                if isinstance(list_reply, dict):
                    return self._clean(list_reply.get("title")) or self._clean(
                        list_reply.get("id")
                    )
            return ""

        return ""

    def _clean(self, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()
