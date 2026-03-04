"""Assist endpoint for core API."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from api.agent_service import AgentService
from api.auth import validate_token
from api.dependencies import get_agent_service
from api.handlers import process_request, stream_request
from api.models import AgentAssistRequest, AgentAssistResponse

router = APIRouter()


async def stream_sse_response(request: AgentAssistRequest, agent_service):
    try:
        async for message in stream_request(request, agent_service):
            data = json.dumps(message.model_dump())
            yield f"event: message\\ndata: {data}\\n\\n"
            await asyncio.sleep(0.01)
    except Exception as exc:  # pylint: disable=broad-except
        error_data = json.dumps({"type": "error", "content": str(exc)})
        yield f"event: error\\ndata: {error_data}\\n\\n"


@router.post("/api/agent/assist", response_model=AgentAssistResponse)
async def agent_assist(
    assist_request: AgentAssistRequest,
    token: str = Depends(validate_token),
    agent_service: AgentService = Depends(get_agent_service),
):
    _ = token
    try:
        if assist_request.streamResponse:
            return StreamingResponse(
                stream_sse_response(assist_request, agent_service),
                media_type="text/event-stream",
            )
        return await process_request(assist_request, agent_service)
    except Exception as exc:  # pylint: disable=broad-except
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing request: {exc}",
        ) from exc
