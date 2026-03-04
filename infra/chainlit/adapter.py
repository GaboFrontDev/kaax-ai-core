"""Adapter helpers for the Chainlit channel in this core repo."""

from __future__ import annotations

from typing import Any

from api.models import AgentAssistRequest, AgentAssistResponse


class ChainlitAdapter:
    async def normalize_inbound(self, raw: dict[str, object]) -> AgentAssistRequest:
        return AgentAssistRequest(
            userText=str(raw.get("message", "")).strip(),
            requestor=str(raw.get("user", "chainlit:user")).strip() or "chainlit:user",
            sessionId=str(raw.get("thread_id", "chainlit:thread")).strip() or "chainlit:thread",
            streamResponse=bool(raw.get("stream", False)),
            promptName=self._optional_string(raw.get("prompt_name")),
            modelName=self._optional_string(raw.get("model_name")),
        )

    async def denormalize_outbound(
        self, response: AgentAssistResponse | dict[str, Any]
    ) -> dict[str, object]:
        if isinstance(response, AgentAssistResponse):
            return {
                "content": response.response,
                "conversation_id": response.conversation_id,
                "run_id": response.run_id,
                "tools_used": list(response.tools_used),
                "completion_time": response.completion_time,
            }

        return {
            "content": str(response.get("response", "")),
            "conversation_id": response.get("conversation_id"),
            "run_id": response.get("run_id"),
            "tools_used": response.get("tools_used") or [],
            "completion_time": response.get("completion_time"),
        }

    def _optional_string(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
