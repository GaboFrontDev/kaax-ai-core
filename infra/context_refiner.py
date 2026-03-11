"""Context refiner: distills conversation history into a compact memory block.

Triggered only when the funnel stage changes (discovery → qualification → capture).
Uses Nova Lite to keep cost minimal — typically 2-3 calls per conversation lifetime.

The refined summary is persisted in the conversations table and reused across turns
until the next stage transition.
"""

from __future__ import annotations

import logging
from typing import List

from langchain_core.messages import BaseMessage, HumanMessage

from settings import MODEL_ROUTER_DEFAULT

logger = logging.getLogger(__name__)

_SUMMARY_PROMPT = (
    "Eres un asistente de memoria para un agente de ventas. "
    "Resume en máximo 5 puntos breves y concisos la siguiente conversación. "
    "Incluye: nombre del cliente (si lo mencionó), su negocio/producto, "
    "objetivo principal (ventas/atención/citas/marketing), volumen de mensajes, "
    "intención de compra y cualquier dato de contacto mencionado. "
    "Máximo 120 palabras. No uses bullet points, usa texto corrido.\n\n"
)


def _format_messages(messages: List[BaseMessage], max_messages: int = 40) -> str:
    lines: list[str] = []
    for m in messages[-max_messages:]:
        content = m.content if isinstance(m.content, str) else str(m.content)
        content = content.strip()
        if not content:
            continue
        role = "Cliente" if isinstance(m, HumanMessage) else "Kaax"
        lines.append(f"{role}: {content[:300]}")
    return "\n".join(lines)


async def build_summary(
    messages: List[BaseMessage],
    prior_summary: str | None = None,
) -> str:
    """Generate a compact summary of the conversation using Nova Lite.

    If a prior_summary exists, it is prepended so the new summary is cumulative
    without needing to re-read old messages.
    """
    from model_builder import get_model

    conversation_text = _format_messages(messages)
    if not conversation_text:
        return prior_summary or ""

    context = ""
    if prior_summary:
        context = f"Resumen previo de la conversación:\n{prior_summary}\n\nMensajes nuevos:\n"

    model = get_model(model_name=MODEL_ROUTER_DEFAULT, temperature=0, streaming=False)
    try:
        result = await model.ainvoke([
            HumanMessage(content=_SUMMARY_PROMPT + context + conversation_text)
        ])
        summary = result.content if isinstance(result.content, str) else str(result.content)
        return summary.strip()
    except Exception:  # pylint: disable=broad-except
        logger.warning("context_refiner: Nova Lite call failed, returning prior summary")
        return prior_summary or ""


async def maybe_refresh_summary(
    thread_id: str,
    messages: List[BaseMessage],
    current_etapa: str,
) -> str:
    """Load persisted summary; regenerate with Nova Lite only if the funnel stage changed.

    Returns the best available summary (possibly empty string on first turn).
    """
    from infra.follow_up.db import get_conversation_memory, update_conversation_memory

    stored_summary, stored_etapa = await get_conversation_memory(thread_id)

    # No stage change — reuse stored summary
    if stored_etapa == current_etapa and stored_summary:
        logger.debug(
            "context_refiner: reusing stored summary etapa=%s thread=%s",
            current_etapa, thread_id,
        )
        return stored_summary

    # Stage changed (or first time) — regenerate
    logger.info(
        "context_refiner: regenerating summary %s→%s thread=%s msgs=%d",
        stored_etapa, current_etapa, thread_id, len(messages),
    )
    new_summary = await build_summary(messages, prior_summary=stored_summary)

    if new_summary:
        await update_conversation_memory(thread_id, new_summary, current_etapa)

    return new_summary
