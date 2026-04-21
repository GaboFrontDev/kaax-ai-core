"""WhatsApp conversation flow with semantic handoff routing."""

from __future__ import annotations

import logging
from typing import Any, Literal, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from api.handlers import process_request
from api.models import AgentAssistRequest
from infra.follow_up.db import (
    HANDOFF_RELEASED_CONTROL,
    get_handoff_requested,
    get_recent_messages,
    is_control_message,
    set_handoff_requested,
)
from infra.whatsapp_meta.client import send_meta_text_message
from model_builder import get_model
from settings import (
    BEDROCK_MODEL,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_NOTIFY_TO,
)

logger = logging.getLogger(__name__)

_HANDOFF_ACK = "Te pasamos con una persona del equipo. En breve te atendemos por aqui."

_CLASSIFIER_PROMPT = """
Eres un clasificador de handoff para conversaciones de WhatsApp.

Debes decidir si la conversacion debe pasar a una persona humana en este turno.
Usa el significado del mensaje y el contexto reciente, no listas de frases exactas.

Activa handoff cuando aplique claramente alguno de estos casos:
- La persona pide hablar con alguien del equipo humano.
- La conversacion esta atascada o repitiendo intentos sin avanzar.
- Hay queja, molestia, excepcion operativa o una situacion sensible donde conviene juicio humano.

No actives handoff por preguntas normales de producto, catalogo, precios, disponibilidad,
agendado o informacion comercial que el asistente puede manejar.

Responde con decision conservadora: si hay duda leve, no actives handoff.
""".strip()


class HandoffAssessment(BaseModel):
    should_handoff: bool = Field(description="Whether this turn should route to a human.")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: Literal[
        "explicit_human_request",
        "conversation_stuck",
        "sensitive_case",
        "none",
    ]
    rationale: str = Field(description="Short explanation grounded in the latest turn and context.")


class WhatsAppFlowState(TypedDict, total=False):
    assist_request: AgentAssistRequest
    agent_service: Any
    session_id: str
    phone_number: str
    phone_number_id: str
    recent_messages: list[tuple[str, str]]
    handoff_active: bool
    handoff_release_pending: bool
    handoff_requested: bool
    handoff_confidence: float
    handoff_reason: str
    handoff_rationale: str
    reply_text: str
    should_send_reply: bool
    notify_admin: bool


def _format_recent_messages(messages: list[tuple[str, str]]) -> str:
    if not messages:
        return "(sin historial reciente)"

    role_labels = {
        "human": "Usuario",
        "agent": "Asistente",
        "admin": "Admin",
    }
    lines: list[str] = []
    for role, content in messages:
        if is_control_message(content):
            continue
        label = role_labels.get(role, role)
        snippet = content.strip()
        if len(snippet) > 220:
            snippet = f"{snippet[:220]}..."
        lines.append(f"{label}: {snippet}")
    return "\n".join(lines)


def _has_pending_handoff_release(messages: list[tuple[str, str]]) -> bool:
    release_index: int | None = None
    for index in range(len(messages) - 1, -1, -1):
        role, content = messages[index]
        if role == "admin" and content == HANDOFF_RELEASED_CONTROL:
            release_index = index
            break

    if release_index is None:
        return False

    for role, content in messages[release_index + 1 :]:
        if role == "agent":
            return False
        if role == "admin" and not is_control_message(content):
            return False
    return True


def _build_handoff_notification(state: WhatsAppFlowState) -> str:
    last_user_text = state["assist_request"].userText.strip()
    if len(last_user_text) > 220:
        last_user_text = f"{last_user_text[:220]}..."

    lines = [
        "Nuevo handoff solicitado",
        f"Numero: {state['phone_number']}",
        f"Thread: {state['session_id']}",
        f"Motivo: {state.get('handoff_reason', 'unknown')}",
        f"Confianza: {state.get('handoff_confidence', 0.0):.2f}",
        f"Detalle: {state.get('handoff_rationale', '')}",
        f'Ultimo mensaje: "{last_user_text}"',
    ]
    history = _format_recent_messages(state.get("recent_messages", []))
    if history:
        lines.append("Historial reciente:")
        lines.append(history)
    return "\n".join(lines)


class WhatsAppConversationGraph:
    def __init__(self) -> None:
        graph = StateGraph(WhatsAppFlowState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("hold_for_human", self._hold_for_human)
        graph.add_node("analyze_handoff", self._analyze_handoff)
        graph.add_node("activate_handoff", self._activate_handoff)
        graph.add_node("notify_admin", self._notify_admin)
        graph.add_node("run_agent", self._run_agent)

        graph.add_edge(START, "load_context")
        graph.add_conditional_edges(
            "load_context",
            self._route_after_context,
            {
                "hold_for_human": "hold_for_human",
                "run_agent": "run_agent",
                "analyze_handoff": "analyze_handoff",
            },
        )
        graph.add_edge("hold_for_human", END)
        graph.add_conditional_edges(
            "analyze_handoff",
            self._route_after_handoff_analysis,
            {
                "activate_handoff": "activate_handoff",
                "run_agent": "run_agent",
            },
        )
        graph.add_edge("activate_handoff", "notify_admin")
        graph.add_edge("notify_admin", END)
        graph.add_edge("run_agent", END)
        self._graph = graph.compile()

    async def run(
        self,
        *,
        assist_request: AgentAssistRequest,
        agent_service: Any,
        session_id: str,
        phone_number: str,
        phone_number_id: str,
    ) -> WhatsAppFlowState:
        result = await self._graph.ainvoke(
            {
                "assist_request": assist_request,
                "agent_service": agent_service,
                "session_id": session_id,
                "phone_number": phone_number,
                "phone_number_id": phone_number_id,
            }
        )
        return result

    async def _load_context(self, state: WhatsAppFlowState) -> WhatsAppFlowState:
        session_id = state["session_id"]
        recent_messages = await get_recent_messages(session_id, limit=8)
        return {
            "handoff_active": await get_handoff_requested(session_id),
            "handoff_release_pending": _has_pending_handoff_release(recent_messages),
            "recent_messages": recent_messages,
        }

    def _route_after_context(
        self,
        state: WhatsAppFlowState,
    ) -> Literal["hold_for_human", "run_agent", "analyze_handoff"]:
        if state.get("handoff_active"):
            return "hold_for_human"
        if state.get("handoff_release_pending"):
            return "run_agent"
        return "analyze_handoff"

    async def _hold_for_human(self, state: WhatsAppFlowState) -> WhatsAppFlowState:
        logger.info("whatsapp_graph handoff already active session=%s", state["session_id"])
        return {
            "handoff_requested": True,
            "handoff_confidence": 1.0,
            "handoff_reason": "already_active",
            "handoff_rationale": "Conversation is already assigned to human handoff.",
            "should_send_reply": False,
            "notify_admin": False,
        }

    async def _analyze_handoff(self, state: WhatsAppFlowState) -> WhatsAppFlowState:
        request = state["assist_request"]
        if not request.userText.strip():
            return {
                "handoff_requested": False,
                "handoff_confidence": 0.0,
                "handoff_reason": "none",
                "handoff_rationale": "Empty user message.",
            }

        model_name = request.modelName or BEDROCK_MODEL
        model = get_model(model_name=model_name, streaming=False, temperature=0.0)
        classifier = model.with_structured_output(HandoffAssessment)
        history = _format_recent_messages(state.get("recent_messages", []))

        try:
            assessment = await classifier.ainvoke(
                [
                    SystemMessage(content=_CLASSIFIER_PROMPT),
                    HumanMessage(
                        content=(
                            "Canal: WhatsApp\n"
                            f"Historial reciente:\n{history}\n\n"
                            f"Ultimo mensaje del usuario:\n{request.userText.strip()}\n"
                        )
                    ),
                ]
            )
        except Exception:
            logger.exception(
                "whatsapp_graph handoff analysis failed session=%s",
                state["session_id"],
            )
            return {
                "handoff_requested": False,
                "handoff_confidence": 0.0,
                "handoff_reason": "none",
                "handoff_rationale": "Classifier failed open.",
            }

        should_handoff = bool(assessment.should_handoff and assessment.confidence >= 0.68)
        return {
            "handoff_requested": should_handoff,
            "handoff_confidence": assessment.confidence,
            "handoff_reason": assessment.reason if should_handoff else "none",
            "handoff_rationale": assessment.rationale,
        }

    def _route_after_handoff_analysis(
        self,
        state: WhatsAppFlowState,
    ) -> Literal["activate_handoff", "run_agent"]:
        if state.get("handoff_requested"):
            return "activate_handoff"
        return "run_agent"

    async def _activate_handoff(self, state: WhatsAppFlowState) -> WhatsAppFlowState:
        changed = await set_handoff_requested(state["session_id"], True)
        logger.info(
            "whatsapp_graph handoff activated session=%s changed=%s reason=%s confidence=%.2f",
            state["session_id"],
            changed,
            state.get("handoff_reason"),
            state.get("handoff_confidence", 0.0),
        )
        return {
            "reply_text": _HANDOFF_ACK,
            "should_send_reply": True,
            "notify_admin": changed,
        }

    async def _notify_admin(self, state: WhatsAppFlowState) -> WhatsAppFlowState:
        if not state.get("notify_admin"):
            return {}
        if not WHATSAPP_NOTIFY_TO:
            return {}
        if not WHATSAPP_META_ACCESS_TOKEN or not state.get("phone_number_id"):
            logger.warning(
                "whatsapp_graph handoff notification skipped session=%s missing credentials",
                state["session_id"],
            )
            return {}

        try:
            await send_meta_text_message(
                api_version=WHATSAPP_META_API_VERSION,
                phone_number_id=state["phone_number_id"],
                access_token=WHATSAPP_META_ACCESS_TOKEN,
                to=WHATSAPP_NOTIFY_TO,
                text=_build_handoff_notification(state),
            )
        except Exception:
            logger.exception(
                "whatsapp_graph handoff notification failed session=%s",
                state["session_id"],
            )
        return {}

    async def _run_agent(self, state: WhatsAppFlowState) -> WhatsAppFlowState:
        response = await process_request(state["assist_request"], state["agent_service"])
        return {
            "reply_text": response.response.strip(),
            "should_send_reply": True,
        }


whatsapp_conversation_graph = WhatsAppConversationGraph()
