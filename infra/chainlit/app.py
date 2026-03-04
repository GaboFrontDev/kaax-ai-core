from __future__ import annotations

from collections import defaultdict, deque
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import chainlit as cl
import httpx

# Ensure project-root imports (e.g. `api.*`) when Chainlit loads this file.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.models import AgentAssistResponse  # noqa: E402
from infra.chainlit.adapter import ChainlitAdapter  # noqa: E402

logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("CHAINLIT_API_URL", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("CHAINLIT_API_TOKEN", "dev-token")
REQUEST_TIMEOUT_SECONDS = float(os.getenv("CHAINLIT_API_TIMEOUT_SECONDS", "90"))
DEFAULT_PROMPT_NAME = (os.getenv("CHAINLIT_PROMPT_NAME") or "").strip() or None
DEFAULT_TOOL_CHOICE = (
    os.getenv("CHAINLIT_TOOL_CHOICE") or "required"
).strip() or "required"
SHOW_TOOL_EVENTS = (
    os.getenv("CHAINLIT_SHOW_TOOL_EVENTS") or "true"
).strip().lower() in {"1", "true", "yes", "on"}


async def _parse_error_detail(response: httpx.Response) -> str:
    body = await response.aread()
    detail = body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(detail)
        detail = str(parsed.get("detail", parsed))
    except Exception:
        pass
    return detail


async def _iter_sse_events(response: httpx.Response):
    event_name = "message"
    data_parts: list[str] = []

    async for raw_line in response.aiter_lines():
        line = (raw_line or "").rstrip("\r")

        if not line:
            if data_parts:
                yield event_name, "\n".join(data_parts)
            event_name = "message"
            data_parts = []
            continue

        if line.startswith(":"):
            continue

        if line.startswith("event:"):
            event_name = line.partition(":")[2].strip() or "message"
            continue

        if line.startswith("data:"):
            data_parts.append(line.partition(":")[2].lstrip())

    if data_parts:
        yield event_name, "\n".join(data_parts)


async def _send_non_stream_response(
    response: httpx.Response, adapter: ChainlitAdapter
) -> None:
    body = response.json()
    assist_response = AgentAssistResponse.model_validate(body)
    normalized = await adapter.denormalize_outbound(assist_response)
    answer = str(normalized.get("content", "")).strip()
    if not answer:
        answer = "No se generó respuesta del agente."
    await cl.Message(content=answer).send()


def _tool_label(tool_name: str) -> str:
    return f"Tool: {tool_name}"


async def _handle_tool_start(
    pending_tool_steps: dict[str, deque[cl.Step]],
    *,
    tool_name: str,
    tool_inputs: Any,
) -> None:
    step = cl.Step(
        name=_tool_label(tool_name),
        type="tool",
        default_open=False,
        show_input="json",
    )
    if tool_inputs is not None:
        step.input = tool_inputs
    step.output = "Ejecutando..."
    await step.send()
    pending_tool_steps[tool_name].append(step)


async def _handle_tool_result(
    pending_tool_steps: dict[str, deque[cl.Step]],
    *,
    tool_name: str,
    tool_result: Any,
) -> None:
    queue_for_tool = pending_tool_steps.get(tool_name)
    if queue_for_tool and queue_for_tool:
        step = queue_for_tool.popleft()
    else:
        step = cl.Step(
            name=_tool_label(tool_name),
            type="tool",
            default_open=False,
            show_input="json",
        )
        step.output = "Resultado disponible."
        await step.send()

    if tool_result is not None:
        step.output = tool_result
    else:
        step.output = "Sin resultado."
    await step.update()


def _requestor() -> str:
    user = cl.user_session.get("user")
    if isinstance(user, str) and user.strip():
        return user.strip()
    return "local"


@cl.on_chat_start
async def on_chat_start() -> None:
    thread_id = f"chainlit:{cl.context.session.id}"
    cl.user_session.set("thread_id", thread_id)
    logger.info("chainlit_chat_start thread_id=%s", thread_id)


@cl.on_message
async def on_message(message: cl.Message) -> None:
    thread_id = str(
        cl.user_session.get("thread_id") or f"chainlit:{cl.context.session.id}"
    )
    adapter = ChainlitAdapter()

    request_payload = await adapter.normalize_inbound(
        {
            "message": message.content,
            "user": f"chainlit:{_requestor()}",
            "thread_id": thread_id,
            "stream": True,
            "tool_choice": DEFAULT_TOOL_CHOICE,
            "prompt_name": DEFAULT_PROMPT_NAME,
        }
    )
    payload: dict[str, Any] = request_payload.model_dump(exclude_none=True)

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    url = f"{API_BASE_URL}/api/agent/assist"

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            async with client.stream(
                "POST", url, json=payload, headers=headers
            ) as response:
                if response.status_code >= 400:
                    detail = await _parse_error_detail(response)
                    await cl.Message(
                        content=f"Error API ({response.status_code}): {detail}"
                    ).send()
                    return

                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type.lower():
                    body = await response.aread()
                    fallback = httpx.Response(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=body,
                        request=response.request,
                    )
                    await _send_non_stream_response(fallback, adapter)
                    return

                stream_message = cl.Message(content="")
                await stream_message.send()
                seen_content = False
                saw_tool_event = False
                tools_used_from_complete: list[str] = []
                pending_tool_steps: dict[str, deque[cl.Step]] = defaultdict(deque)

                async for event_name, raw_data in _iter_sse_events(response):
                    if event_name == "error":
                        error_detail = raw_data
                        try:
                            parsed_error = json.loads(raw_data)
                            error_detail = str(parsed_error.get("content", raw_data))
                        except Exception:
                            pass
                        await cl.Message(
                            content=f"Error de streaming desde API: {error_detail}"
                        ).send()
                        return

                    if event_name != "message":
                        continue

                    try:
                        payload_message = json.loads(raw_data)
                    except json.JSONDecodeError:
                        continue

                    if payload_message.get("type") == "content":
                        token = str(payload_message.get("content", ""))
                        if token:
                            seen_content = True
                            await stream_message.stream_token(token)

                    if SHOW_TOOL_EVENTS and payload_message.get("type") == "tool_start":
                        saw_tool_event = True
                        tool_name = str(payload_message.get("tool") or "unknown_tool")
                        await _handle_tool_start(
                            pending_tool_steps,
                            tool_name=tool_name,
                            tool_inputs=payload_message.get("inputs"),
                        )

                    if (
                        SHOW_TOOL_EVENTS
                        and payload_message.get("type") == "tool_result"
                    ):
                        saw_tool_event = True
                        tool_name = str(payload_message.get("tool") or "unknown_tool")
                        await _handle_tool_result(
                            pending_tool_steps,
                            tool_name=tool_name,
                            tool_result=payload_message.get("result"),
                        )

                    if payload_message.get("type") == "complete":
                        raw_tools = payload_message.get("tools_used") or []
                        if isinstance(raw_tools, list):
                            tools_used_from_complete = [
                                str(item).strip()
                                for item in raw_tools
                                if str(item).strip()
                            ]
                        break

                if not seen_content:
                    stream_message.content = "No se generó respuesta del agente."
                    await stream_message.update()
                else:
                    await stream_message.update()

                if SHOW_TOOL_EVENTS and not saw_tool_event and tools_used_from_complete:
                    tools_text = ", ".join(sorted(set(tools_used_from_complete)))
                    await cl.Message(content=f"Tools usados: {tools_text}").send()
    except Exception as exc:
        logger.exception("chainlit_message_error")
        await cl.Message(
            content=f"No se pudo conectar con la API: {type(exc).__name__}: {exc}"
        ).send()
