"""Minimal agent builder that keeps the original project conventions."""

from __future__ import annotations

from typing import Any, List, Optional

from langchain.agents import create_agent

from model_builder import get_model
from prompt_factory import PromptFactory
from session_manager import SessionManager
from settings import BEDROCK_MODEL, DEFAULT_PROMPT_NAME, DEFAULT_TEMPERATURE
from tools import echo_tool, simple_math_tool



def build_tools(
    checkpointer: Optional[SessionManager] = None,
    email: str = "",
    stores: Optional[dict] = None,
):
    """Return a minimal list of example tools.

    Signature intentionally mirrors the legacy project convention.
    """
    _ = checkpointer
    _ = email
    _ = stores
    return [
        echo_tool,
        simple_math_tool,
    ]



def build_agent(
    model_name: str = BEDROCK_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    prompt_name: str = DEFAULT_PROMPT_NAME,
    checkpointer: Optional[SessionManager] = None,
    email: str = "",
    middleware: Optional[List[Any]] = None,
    tools: Optional[List[Any]] = None,
    model: Optional[Any] = None,
    prompt_factory: Optional[PromptFactory] = None,
    stores: Optional[dict] = None,
):
    """Build and return a minimal LangChain/LangGraph agent."""
    if middleware is None:
        middleware = []

    if checkpointer is None:
        checkpointer = SessionManager()

    if tools is None:
        tools = build_tools(checkpointer=checkpointer, email=email, stores=stores)

    if model is None:
        model = get_model(model_name=model_name, temperature=temperature)

    if prompt_factory is None:
        prompt_factory = PromptFactory()

    try:
        system_prompt = prompt_factory.load_prompt(prompt_name)
    except ValueError:
        system_prompt = prompt_factory.load_prompt(DEFAULT_PROMPT_NAME)

    return create_agent(
        model,
        tools,
        checkpointer=checkpointer,
        system_prompt=system_prompt,
        middleware=middleware,
    )
