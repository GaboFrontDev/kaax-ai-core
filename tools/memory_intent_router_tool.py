"""Tool to route intent to the appropriate knowledge/memory node.

Called when the user asks about pricing, plans, implementation, or when
the conversation goal changes abruptly.
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class MemoryIntentRouterInput(BaseModel):
    user_text: str = Field(..., description="Latest user message text exactly as received.")
    intent_hint: str | None = Field(
        default=None,
        description=(
            "Optional detected intent hint: "
            "'pricing', 'implementation', 'goal_change', or 'other'."
        ),
    )


_PRICING_KEYWORDS = frozenset(
    ["precio", "precios", "plan", "planes", "costo", "cuanto cuesta", "ver planes", "implementacion"]
)
_GOAL_CHANGE_KEYWORDS = frozenset(
    ["en realidad", "mejor dicho", "quiero cambiar", "no quiero", "olvida", "me equivoque"]
)


@tool(args_schema=MemoryIntentRouterInput)
async def memory_intent_router_tool(
    user_text: str,
    intent_hint: str | None = None,
) -> dict:
    """Route intent to the appropriate knowledge or memory node.

    Call this when:
    - User asks about pricing, plans, or implementation.
    - User's conversation goal changes abruptly.

    Returns routing metadata the agent uses to select the right response strategy.
    """
    norm = user_text.lower().strip()

    detected_intent = intent_hint or "other"
    if any(kw in norm for kw in _PRICING_KEYWORDS):
        detected_intent = "pricing"
    elif any(kw in norm for kw in _GOAL_CHANGE_KEYWORDS):
        detected_intent = "goal_change"
    elif "demo" in norm or "agendar" in norm:
        detected_intent = "demo"

    return {
        "routed_to": detected_intent,
        "user_text": user_text,
        "should_include_pricing_link": detected_intent == "pricing",
        "should_include_demo_link": detected_intent in ("demo", "pricing"),
        "goal_changed": detected_intent == "goal_change",
    }
