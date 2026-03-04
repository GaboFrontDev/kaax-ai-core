"""Core API handlers for non-streaming and streaming agent responses."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, AsyncGenerator

from langchain_core.messages import HumanMessage
from langchain_core.messages.ai import AIMessageChunk

from api.callback_handler import APICallbackHandler
from api.checkpoint_repair import repair_dangling_tool_calls
from api.models import (
    AgentAssistRequest,
    AgentAssistResponse,
    StreamingMessage,
    StreamingMessageType,
)

logger = logging.getLogger(__name__)

THINKING_OPEN_TAG_PREFIX = "<thinking"
THINKING_CLOSE_TAG = "</thinking>"


def _strip_thinking_blocks(text: str) -> str:
    cleaned = re.sub(
        r"<thinking[^>]*>.*?</thinking>",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"</?thinking[^>]*>", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _longest_suffix_that_is_prefix(value: str, prefix: str) -> int:
    max_size = min(len(value), len(prefix) - 1)
    for size in range(max_size, 0, -1):
        if prefix.startswith(value[-size:]):
            return size
    return 0


def _filter_thinking_stream_text(text: str, state: dict[str, Any]) -> str:
    """Remove <thinking> blocks from a streaming text sequence."""
    visible_parts: list[str] = []
    working = f"{state['carry']}{text}"
    state["carry"] = ""

    while working:
        if state["inside_thinking"]:
            end_index = working.find(THINKING_CLOSE_TAG)
            if end_index == -1:
                keep = min(len(working), len(THINKING_CLOSE_TAG) - 1)
                state["carry"] = working[-keep:] if keep else ""
                return "".join(visible_parts)

            working = working[end_index + len(THINKING_CLOSE_TAG) :]
            state["inside_thinking"] = False
            continue

        start_index = working.find(THINKING_OPEN_TAG_PREFIX)
        if start_index == -1:
            partial = _longest_suffix_that_is_prefix(working, THINKING_OPEN_TAG_PREFIX)
            if partial:
                visible_parts.append(working[:-partial])
                state["carry"] = working[-partial:]
            else:
                visible_parts.append(working)
            return "".join(visible_parts)

        visible_parts.append(working[:start_index])
        working = working[start_index:]

        open_tag_end = working.find(">")
        if open_tag_end == -1:
            state["carry"] = working
            return "".join(visible_parts)

        working = working[open_tag_end + 1 :]
        state["inside_thinking"] = True

    return "".join(visible_parts)


def _parse_json_if_possible(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _ensure_json_serializable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {
                str(key): _ensure_json_serializable(item) for key, item in value.items()
            }
        if isinstance(value, list):
            return [_ensure_json_serializable(item) for item in value]
        return str(value)


def _normalize_tool_output(tool_output: Any) -> dict[str, Any]:
    if tool_output is None:
        return {"content": None}

    if hasattr(tool_output, "model_dump"):
        try:
            return _ensure_json_serializable(tool_output.model_dump())
        except Exception:  # pylint: disable=broad-except
            pass

    if hasattr(tool_output, "content"):
        normalized: dict[str, Any] = {
            "content": _parse_json_if_possible(getattr(tool_output, "content"))
        }

        if hasattr(tool_output, "artifact"):
            artifact = getattr(tool_output, "artifact")
            if artifact is not None:
                normalized["artifact"] = artifact

        if hasattr(tool_output, "name"):
            name = getattr(tool_output, "name")
            if name:
                normalized["name"] = name

        return _ensure_json_serializable(normalized)

    if isinstance(tool_output, dict):
        return _ensure_json_serializable(tool_output)

    return {"content": _ensure_json_serializable(_parse_json_if_possible(tool_output))}


def _extract_content_as_text(content) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(text, dict) and isinstance(text.get("value"), str):
                    parts.append(text["value"])
        return "".join(parts)

    return str(content)


def _build_config(
    request: AgentAssistRequest,
    callback_handler: APICallbackHandler,
    session_id: str,
) -> dict:
    return {
        "configurable": {"thread_id": session_id},
        "tool_choice": request.toolChoice or "auto",
        "callbacks": [callback_handler],
        "metadata": {"user_email": request.requestor},
    }


async def process_request(
    request: AgentAssistRequest, agent_service
) -> AgentAssistResponse:
    start_time = time.time()
    callback_handler = APICallbackHandler()
    agent = agent_service.create_agent_for_request(request, callback_handler)

    session_id = request.sessionId or f"core-api-{int(time.time())}"
    config = _build_config(request, callback_handler, session_id)

    await repair_dangling_tool_calls(agent, config, session_id)

    response = await agent.ainvoke(
        {"messages": [HumanMessage(content=request.userText)]},
        config=config,
    )

    ai_message = response["messages"][-1].content
    completion_time = time.time() - start_time

    return AgentAssistResponse(
        response=_strip_thinking_blocks(_extract_content_as_text(ai_message)),
        tools_used=sorted(set(callback_handler.tools_used)),
        completion_time=round(completion_time, 2),
        conversation_id=session_id,
        run_id=callback_handler.root_run_id,
    )


async def stream_request(
    request: AgentAssistRequest,
    agent_service,
) -> AsyncGenerator[StreamingMessage, None]:
    callback_handler = APICallbackHandler()
    agent = agent_service.create_agent_for_request(request, callback_handler)

    session_id = request.sessionId or f"core-api-{int(time.time())}"
    config = _build_config(request, callback_handler, session_id)

    await repair_dangling_tool_calls(agent, config, session_id)

    run_id = None
    thinking_state = {"inside_thinking": False, "carry": ""}

    async for event in agent.astream_events(
        {"messages": [HumanMessage(content=request.userText)]},
        config=config,
        version="v2",
    ):
        kind = event["event"]
        data = event["data"]
        name = event.get("name")

        if kind == "on_chain_start" and name == "LangGraph":
            run_id = str(event["run_id"])

        if kind == "on_chat_model_stream":
            chunk = data["chunk"]
            content = ""

            if isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, str):
                content = chunk.content
            elif isinstance(chunk, AIMessageChunk) and isinstance(chunk.content, list):
                parts: list[str] = []
                for block in chunk.content:
                    if not isinstance(block, dict) or block.get("type") != "text":
                        continue
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    elif isinstance(text, dict) and isinstance(text.get("value"), str):
                        parts.append(text["value"])
                content = "".join(parts)

            content = _filter_thinking_stream_text(content, thinking_state)

            if content and content.strip():
                yield StreamingMessage(
                    type=StreamingMessageType.CONTENT,
                    content=content,
                    conversation_id=session_id,
                    run_id=run_id,
                )

        elif kind == "on_tool_start":
            tool_input = data.get("input")

            try:
                json.dumps(tool_input)
                inputs_for_wire = tool_input
            except TypeError:
                inputs_for_wire = json.loads(json.dumps(tool_input, default=str))

            yield StreamingMessage(
                type=StreamingMessageType.TOOL_START,
                tool=name,
                inputs=inputs_for_wire,
                conversation_id=session_id,
                run_id=run_id,
            )

        elif kind == "on_tool_end":
            tool_output = data.get("output")
            output_for_wire = _normalize_tool_output(tool_output)

            yield StreamingMessage(
                type=StreamingMessageType.TOOL_RESULT,
                tool=name,
                result=output_for_wire,
                conversation_id=session_id,
                run_id=run_id,
            )

    if run_id is None and callback_handler.root_run_id:
        run_id = callback_handler.root_run_id

    yield StreamingMessage(
        type=StreamingMessageType.COMPLETE,
        content="Request complete",
        tools_used=sorted(set(callback_handler.tools_used)),
        conversation_id=session_id,
        run_id=run_id,
    )
