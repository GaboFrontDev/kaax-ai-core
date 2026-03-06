"""Normalize Twilio Voice webhook payloads into core API models."""

from __future__ import annotations

from dataclasses import dataclass

from api.models import AgentAssistRequest, AgentAssistResponse


@dataclass(frozen=True)
class TwilioVoiceCall:
    call_sid: str
    from_number: str
    to_number: str
    speech_result: str
    call_status: str = "in-progress"


class TwilioVoiceAdapter:
    def to_assist_request(
        self,
        call: TwilioVoiceCall,
        *,
        prompt_name: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ) -> AgentAssistRequest:
        return AgentAssistRequest(
            userText=call.speech_result,
            requestor=f"voice:{call.from_number}",
            # Each CallSid = one conversation thread in the checkpointer
            sessionId=f"voice:{call.call_sid}",
            streamResponse=False,
            promptName=prompt_name,
            modelName=model_name,
            temperature=temperature,
            # conversation_loop_tool is irrelevant for phone calls and adds ~3s latency
            excludeTools=["conversation_loop_tool"],
            systemContext=self._voice_context(call),
        )

    @staticmethod
    def _voice_context(call: "TwilioVoiceCall") -> str:
        return (
            f"CONTEXTO DE LLAMADA:\n"
            f"- Canal: llamada telefónica (voz)\n"
            f"- Número del llamante: {call.from_number}\n"
            f"- El usuario NO puede hacer clic en links durante la llamada.\n"
            f"- Si el usuario pide demo o un link, dile que se lo enviarás por WhatsApp.\n"
            f"- Si necesitas su número de contacto, pregunta: "
            f"'¿Quieres que te contactemos al número desde el que estás llamando?' "
            f"Si confirma, usa {call.from_number} como contact_phone al llamar capture_lead_if_ready_tool."
        )

    def extract_outbound_text(self, response: AgentAssistResponse) -> str:
        return response.response.strip()
