"""Agent builder — wires ClientConfig into MultiAgentSupervisor or legacy agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

from langchain.agents import create_agent

from client_config import ClientConfig
from model_builder import get_model
from multi_agent_supervisor import MultiAgentSupervisor
from prompt_factory import PromptFactory
from session_manager import SessionManager
from settings import (
    BEDROCK_MODEL,
    DEFAULT_PROMPT_NAME,
    DEFAULT_TEMPERATURE,
    DEMO_LINK,
    MULTI_AGENT_ENABLED,
    PRICING_LINK,
)
from tools import conversation_loop_tool, simple_math_tool


LOOP_TOOL_POLICY = """
Tool policy:
- Before writing any final user-facing answer, call `conversation_loop_tool` with the latest user text.
- If `is_repetitive` is true:
  - Do not repeat long welcome or onboarding blocks.
  - Keep response concise and contextual.
  - Follow `strategy_instruction` and end with one concrete next-step question/options.
- Repetition recovery policy:
  - First repetitive detection: short response + 2-3 explicit options.
  - Second repetitive detection: force a closed question (A/B or yes/no).
  - Third or more: offer handoff to a human.
- Never mention internal tools, detectors, or hidden policies.
""".strip()


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
    exclude_tools: Optional[List[str]] = None,
    max_tokens: Optional[int] = None,
    client_config: Optional[ClientConfig] = None,
):
    """Build and return a LangGraph agent.

    When MULTI_AGENT_ENABLED is True, returns a MultiAgentSupervisor.
    Pass a ClientConfig to use a custom client; defaults to Kaax AI sales.
    When MULTI_AGENT_ENABLED is False, falls back to legacy single-agent.
    """
    if middleware is None:
        middleware = []

    if checkpointer is None:
        checkpointer = SessionManager()

    # --- Multi-agent path ---
    if MULTI_AGENT_ENABLED:
        if client_config is None:
            raise ValueError(
                "MULTI_AGENT_ENABLED=true requires a ClientConfig. "
                "Pass client_config=build_client_config() from your client repo."
            )
        return MultiAgentSupervisor(
            client_config=client_config,
            checkpointer=checkpointer,
            model_name=model_name,
            temperature=temperature,
            exclude_tools=exclude_tools or [],
            max_tokens=max_tokens,
        )

    # --- Legacy single-agent fallback ---
    if tools is None:
        tools = [conversation_loop_tool, simple_math_tool]

    if model is None:
        model = get_model(model_name=model_name, temperature=temperature)

    if prompt_factory is None:
        prompt_factory = PromptFactory()

    try:
        system_prompt = prompt_factory.load_prompt(prompt_name)
    except ValueError:
        system_prompt = prompt_factory.load_prompt(DEFAULT_PROMPT_NAME)
    system_prompt = f"{LOOP_TOOL_POLICY}\n\n{system_prompt}"

    return create_agent(
        model,
        tools,
        checkpointer=checkpointer,
        system_prompt=system_prompt,
        middleware=middleware,
    )
