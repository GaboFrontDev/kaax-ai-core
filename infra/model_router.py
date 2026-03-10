"""Deterministic model router: Nova Lite default, Sonnet fallback on complexity."""

from __future__ import annotations

import re

from settings import (
    BEDROCK_MODEL,
    MODEL_ROUTER_COMPLEXITY_CHARS,
    MODEL_ROUTER_DEFAULT,
    MODEL_ROUTER_FALLBACK,
)

_COMPLEXITY_RE = re.compile(
    r"\b(precio[s]?|costo[s]?|tarifa[s]?|plan[es]*|implement[ar]?|implementaci[oó]n"
    r"|arquitectura|seguridad|contrat[ao]|contratar|factura|facturaci[oó]n"
    r"|integra[cr]|integraci[oó]n|crm|api|t[eé]cnic[ao]|demo|demostraci[oó]n|piloto)\b",
    re.IGNORECASE,
)


def route_model(
    *,
    explicit_model: str | None,
    user_text: str,
    system_context: str = "",
) -> tuple[str, str]:
    """Return (model_id, route_tier).

    Priority:
    1. explicit_model in request  → tier "explicit"
    2. Complexity heuristic       → tier "fallback" (Sonnet)
    3. Default                    → tier "default"  (Nova Lite)
    """
    if explicit_model:
        return explicit_model, "explicit"

    combined = user_text + " " + system_context
    if len(user_text) > MODEL_ROUTER_COMPLEXITY_CHARS or _COMPLEXITY_RE.search(combined):
        return MODEL_ROUTER_FALLBACK, "fallback"

    return MODEL_ROUTER_DEFAULT, "default"
