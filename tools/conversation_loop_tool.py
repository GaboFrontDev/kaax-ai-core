"""Tool to detect repetitive conversation loops and suggest response strategy."""

from __future__ import annotations

from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from tools.conversation_loop_graph import conversation_loop_graph


class ConversationLoopInput(BaseModel):
    user_text: str = Field(
        ...,
        description="Latest user message text exactly as received.",
    )
    scope_key: str | None = Field(
        default=None,
        description=(
            "Optional conversation scope key. If omitted, the tool tries to infer it "
            "from runtime configurable.thread_id."
        ),
    )


def _scope_from_runtime(runtime: ToolRuntime | None) -> str:
    if runtime is None:
        return "unknown"

    config: dict[str, Any] = dict(runtime.config or {})
    configurable = config.get("configurable") or {}
    if isinstance(configurable, dict):
        thread_id = configurable.get("thread_id")
        if thread_id:
            return str(thread_id).strip()

    metadata = config.get("metadata") or {}
    if isinstance(metadata, dict):
        requestor = metadata.get("user_email")
        if requestor:
            return f"requestor:{str(requestor).strip().lower()}"

    return "unknown"


@tool(args_schema=ConversationLoopInput)
async def conversation_loop_tool(
    user_text: str,
    scope_key: str | None = None,
    runtime: ToolRuntime | None = None,
) -> dict:
    """Analyze repetitive low-signal turns and return strategy guidance."""
    resolved_scope = (scope_key or "").strip() or _scope_from_runtime(runtime)
    decision = await conversation_loop_graph.analyze(
        scope_key=resolved_scope,
        user_text=user_text,
    )
    return {
        "is_repetitive": decision.is_repetitive,
        "repetition_count": decision.repetition_count,
        "normalized_text": decision.normalized_text,
        "strategy_instruction": decision.strategy_instruction or "",
        "scope_key": resolved_scope,
    }
