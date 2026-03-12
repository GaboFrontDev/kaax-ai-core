"""Client configuration for the MultiAgentSupervisor engine.

Each client (Kaax Sales, Tienda Pintura, etc.) declares a ClientConfig that tells
the engine what state class, tools, prompts, and specialists to use.

Loaded from a YAML file via load_client_config(), or built programmatically.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from base_conversation_state import BaseConversationState

logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    """Everything the engine needs to run a specific client's agent."""

    name: str

    # The ConversationState subclass to instantiate each turn
    state_class: type[BaseConversationState]

    # Absolute or relative path to the client's prompts directory
    prompts_dir: str

    # Ordered list of specialist names — must match prompt YAML filenames
    specialists: list[str]

    # Tool instances available to all specialist agents
    tools: list[Any]

    # Models
    model_default: str
    model_fallback: str

    # Tool policy block prepended to every system prompt
    tool_policy: str = ""

    # Per turn-mode instructions injected into system prompt
    # Keys: "first_contact", "identity", "normal"
    turn_mode_instructions: dict[str, str] = field(default_factory=dict)

    # Optional links injected into state summary block
    demo_link: str = ""
    pricing_link: str = ""


def _import_class(dotted_path: str) -> type:
    """Import a class from a dotted path like 'states.kaax.KaaxConversationState'."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _import_tool(dotted_path: str) -> Any:
    """Import a tool instance from a dotted path like 'tools.capture_lead_if_ready_tool.capture_lead_if_ready_tool'."""
    module_path, attr_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr_name)


def load_client_config(config_path: str) -> ClientConfig:
    """Load a ClientConfig from a YAML file.

    Example YAML structure:
        name: kaax_sales
        state_class: conversation_state.ConversationState
        prompts_dir: prompts/
        specialists:
          - discovery
          - qualification
          - capture
          - knowledge
        tools:
          - tools.capture_lead_if_ready_tool.capture_lead_if_ready_tool
          - tools.simple_math_tool.simple_math_tool
        model_default: us.anthropic.claude-haiku-4-5-20251001-v1:0
        model_fallback: global.anthropic.claude-sonnet-4-6
        demo_link: https://calendly.com/...
        pricing_link: https://kaax.ai/#precios
        tool_policy: |
          Tool policy: ...
        turn_mode_instructions:
          first_contact: "TURNO: primer_contacto — ..."
          identity: "TURNO: identidad — ..."
          normal: "TURNO: normal — ..."
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Client config not found: {config_path}")

    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    state_class = _import_class(data["state_class"])
    tools = [_import_tool(t) for t in data.get("tools", [])]

    return ClientConfig(
        name=data["name"],
        state_class=state_class,
        prompts_dir=str(Path(config_path).parent / data.get("prompts_dir", "prompts")),
        specialists=data.get("specialists", ["discovery", "qualification", "capture", "knowledge"]),
        tools=tools,
        model_default=data["model_default"],
        model_fallback=data.get("model_fallback", data["model_default"]),
        tool_policy=data.get("tool_policy", ""),
        turn_mode_instructions=data.get("turn_mode_instructions", {}),
        demo_link=data.get("demo_link", ""),
        pricing_link=data.get("pricing_link", ""),
    )
