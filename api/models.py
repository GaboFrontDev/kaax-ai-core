"""Pydantic models for the minimal core API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel


class AgentAssistRequest(BaseModel):
    userText: str
    requestor: str
    modelName: Optional[str] = None
    temperature: Optional[float] = None
    streamResponse: Optional[bool] = False
    sessionId: Optional[str] = None
    promptName: Optional[str] = None
    toolChoice: Optional[str] = "auto"
    excludeTools: list[str] = []
    systemContext: Optional[str] = None


class AgentAssistResponse(BaseModel):
    response: str
    tools_used: list[str] = []
    completion_time: float
    conversation_id: Optional[str] = None
    run_id: Optional[str] = None


class StreamingMessageType(str, Enum):
    CONTENT = "content"
    TOOL_START = "tool_start"
    TOOL_RESULT = "tool_result"
    COMPLETE = "complete"


class StreamingMessage(BaseModel):
    type: StreamingMessageType
    content: Optional[str] = None
    tool: Optional[str] = None
    inputs: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    tools_used: Optional[list[str]] = None
    conversation_id: Optional[str] = None
    run_id: Optional[str] = None
