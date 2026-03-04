"""Checkpoint repair utility for dangling tool calls in persisted threads."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)

TOOL_ERROR_CONTENT = "Tool execution failed due to an error."



def _find_dangling_tool_calls(messages: list) -> list[dict[str, Any]]:
    if not messages:
        return []

    dangling_tool_calls: list[dict[str, Any]] = []

    for index, msg in enumerate(messages):
        if not isinstance(msg, AIMessage):
            continue

        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            continue

        expected_ids = {tool_call["id"] for tool_call in tool_calls if "id" in tool_call}
        if not expected_ids:
            continue

        found_ids = set()
        for subsequent in messages[index + 1 :]:
            if isinstance(subsequent, ToolMessage):
                tool_call_id = getattr(subsequent, "tool_call_id", None)
                if tool_call_id in expected_ids:
                    found_ids.add(tool_call_id)
            elif isinstance(subsequent, AIMessage):
                break

        missing_ids = expected_ids - found_ids
        for tool_call in tool_calls:
            if tool_call.get("id") in missing_ids:
                dangling_tool_calls.append(tool_call)

    return dangling_tool_calls


async def repair_dangling_tool_calls(agent: Any, config: RunnableConfig, session_id: str) -> bool:
    try:
        state = await agent.aget_state(config)

        if not state or not state.values:
            return False

        messages = state.values.get("messages", [])
        dangling_calls = _find_dangling_tool_calls(messages)

        if not dangling_calls:
            return False

        repair_messages = [
            ToolMessage(
                content=TOOL_ERROR_CONTENT,
                tool_call_id=tool_call["id"],
                name=tool_call.get("name", "unknown_tool"),
            )
            for tool_call in dangling_calls
        ]

        await agent.aupdate_state(config, {"messages": repair_messages}, as_node="tools")
        logger.warning(
            "Repaired %s dangling tool call(s) for session %s",
            len(repair_messages),
            session_id,
        )
        return True
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Error during checkpoint repair for session %s: %s", session_id, exc)
        return False
