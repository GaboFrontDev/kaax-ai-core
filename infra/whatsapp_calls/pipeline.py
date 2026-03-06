"""Agent + Deepgram pipeline for WhatsApp Calling turns."""

from __future__ import annotations

from dataclasses import dataclass

from api.agent_service import AgentService
from api.handlers import process_request
from infra.whatsapp_calls.adapter import WhatsAppCallTurn, WhatsAppCallsAdapter
from infra.whatsapp_calls.deepgram_client import synthesize_stream


@dataclass(frozen=True)
class WhatsAppCallPipelineResult:
    response_text: str
    tts_audio: bytes


class WhatsAppCallPipeline:
    def __init__(self, agent_service: AgentService):
        self._agent_service = agent_service
        self._adapter = WhatsAppCallsAdapter()

    async def handle_turn(
        self,
        turn: WhatsAppCallTurn,
        *,
        prompt_name: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        deepgram_api_key: str = "",
        deepgram_tts_model: str = "aura-2-celeste-es",
    ) -> WhatsAppCallPipelineResult:
        assist_request = self._adapter.to_assist_request(
            turn,
            prompt_name=prompt_name,
            model_name=model_name,
            temperature=temperature,
        )
        assist_response = await process_request(assist_request, self._agent_service)
        response_text = self._adapter.extract_outbound_text(assist_response)
        if not response_text:
            response_text = "Un momento, ¿puedes repetirme tu consulta?"

        if not deepgram_api_key:
            return WhatsAppCallPipelineResult(response_text=response_text, tts_audio=b"")

        chunks: list[bytes] = []
        async for chunk in synthesize_stream(
            response_text,
            deepgram_api_key,
            model=deepgram_tts_model,
        ):
            chunks.append(chunk)
        return WhatsAppCallPipelineResult(response_text=response_text, tts_audio=b"".join(chunks))

