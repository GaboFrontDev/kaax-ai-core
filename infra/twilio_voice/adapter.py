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
        )

    def extract_outbound_text(self, response: AgentAssistResponse) -> str:
        return response.response.strip()
