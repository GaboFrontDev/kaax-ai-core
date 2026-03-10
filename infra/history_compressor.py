"""History compressor: summarize old turns to reduce input token cost."""

from __future__ import annotations

import logging

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


def _total_chars(messages: list[BaseMessage]) -> int:
    return sum(len(str(m.content)) for m in messages)


async def _summarize(messages: list[BaseMessage], model_name: str, temperature: float) -> str:
    from model_builder import get_model

    lines = []
    for m in messages:
        if not hasattr(m, "content"):
            continue
        content = m.content if isinstance(m.content, str) else str(m.content)
        role = "Usuario" if isinstance(m, HumanMessage) else "Agente"
        lines.append(f"{role}: {content[:300]}")

    conversation_text = "\n".join(lines)[:3000]
    model = get_model(model_name=model_name, temperature=temperature, streaming=False)
    result = await model.ainvoke([
        HumanMessage(
            content=(
                "Resume en 2-3 oraciones los puntos clave de esta conversación "
                "(nombre del cliente, necesidad principal, etapa comercial):\n"
                + conversation_text
            )
        )
    ])
    content = result.content
    return content if isinstance(content, str) else str(content)


async def compress_history_if_needed(
    agent,
    config: RunnableConfig,
    *,
    threshold_messages: int,
    threshold_chars: int,
    tail_messages: int,
    compress_model_name: str,
    temperature: float = 0.1,
) -> bool:
    """Compress conversation history if it exceeds thresholds. Returns True if compressed."""
    try:
        state = await agent.aget_state(config)
        if not state or not state.values:
            return False

        messages: list[BaseMessage] = list(state.values.get("messages", []))
        if len(messages) <= threshold_messages and _total_chars(messages) <= threshold_chars:
            return False

        if len(messages) <= tail_messages:
            return False

        to_compress = messages[:-tail_messages]
        if not to_compress:
            return False

        logger.info(
            "history_compressor: compressing %d messages (total=%d chars) thread=%s",
            len(to_compress),
            _total_chars(messages),
            (config or {}).get("configurable", {}).get("thread_id", "?"),
        )

        summary_text = await _summarize(to_compress, compress_model_name, temperature)

        from langgraph.graph.message import RemoveMessage

        removals = [RemoveMessage(id=m.id) for m in to_compress if hasattr(m, "id") and m.id]
        summary_msg = SystemMessage(content=f"[Resumen de conversación anterior]: {summary_text}")
        await agent.aupdate_state(config, {"messages": removals + [summary_msg]})

        logger.info("history_compressor: compressed successfully, summary=%r", summary_text[:80])
        return True

    except Exception:
        logger.exception("history_compressor: failed (fail-open, continuing normally)")
        return False
