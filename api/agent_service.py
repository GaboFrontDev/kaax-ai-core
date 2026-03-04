"""Service that builds an agent per request."""

from __future__ import annotations

import logging

from agent import build_agent
from api.models import AgentAssistRequest
from session_manager import SessionManager
from settings import BEDROCK_MODEL, DEFAULT_TEMPERATURE

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def create_agent_for_request(self, request: AgentAssistRequest, callback_handler):
        model_name = request.modelName or BEDROCK_MODEL
        temperature = (
            request.temperature if request.temperature is not None else DEFAULT_TEMPERATURE
        )

        agent = build_agent(
            model_name=model_name,
            temperature=temperature,
            prompt_name=request.promptName or "agent",
            checkpointer=self.session_manager,
            email=request.requestor,
        )

        logger.info("Created core agent for requestor=%s model=%s", request.requestor, model_name)
        _ = callback_handler
        return agent
