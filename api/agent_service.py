"""Service that builds an agent per request."""

from __future__ import annotations

import logging
from typing import Any

from agent import build_agent
from api.models import AgentAssistRequest
from session_manager import SessionManager
from settings import (
    BEDROCK_MODEL,
    DEFAULT_TEMPERATURE,
    ENABLE_MODEL_ROUTER,
    ENABLE_PROMPT_COMPACT,
    MODEL_MAX_OUTPUT_TOKENS,
)

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def create_agent_for_request(
        self, request: AgentAssistRequest, callback_handler: Any
    ) -> tuple[Any, str]:
        """Return (agent, route_tier).

        route_tier is one of: "explicit", "channel", "fallback", "default".
        """
        route_tier = "explicit" if request.modelName else "default"
        model_name = request.modelName or BEDROCK_MODEL

        if ENABLE_MODEL_ROUTER and not request.modelName:
            from infra.model_router import route_model
            model_name, route_tier = route_model(
                explicit_model=request.modelName,
                user_text=request.userText,
                system_context=request.systemContext or "",
            )

        # Store routed model on callback so usage writer can read it
        callback_handler.model_id = model_name

        temperature = (
            request.temperature if request.temperature is not None else DEFAULT_TEMPERATURE
        )
        max_tokens = MODEL_MAX_OUTPUT_TOKENS if ENABLE_PROMPT_COMPACT else None

        agent = build_agent(
            model_name=model_name,
            temperature=temperature,
            prompt_name=request.promptName or "agent",
            checkpointer=self.session_manager,
            email=request.requestor,
            exclude_tools=request.excludeTools,
            max_tokens=max_tokens,
        )

        logger.info(
            "agent_service: requestor=%s model=%s tier=%s",
            request.requestor, model_name, route_tier,
        )
        _ = callback_handler
        return agent, route_tier
