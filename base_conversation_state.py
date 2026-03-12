"""Abstract base class for conversation state.

Every client must implement this to plug into the MultiAgentSupervisor engine.
Generic utilities (normalize, is_greeting, is_identity_question, contact extraction)
are provided here so clients don't have to reimplement them.
"""

from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Generic text utilities (available to all clients)
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


_GREETING_TOKENS = frozenset([
    "hola", "buenas", "hey", "hi", "hello", "saludos", "buenos", "buen", "ola",
])

_IDENTITY_PATTERNS = [
    r"quien\s+eres",
    r"que\s+eres",
    r"que\s+haces",
    r"como\s+te\s+llamas",
    r"eres\s+(un[ao]?\s+)?(bot|robot|ia|agente|humano|persona)",
    r"habla(s)?\s+con\s+(un\s+)?(humano|persona|agente|robot)",
    r"(eres|es\s+esto)\s+(humano|persona|real|ia|artificial)",
    r"presentate",
    r"presentacion",
]


def is_greeting(text: str) -> bool:
    norm = normalize(text)
    tokens = set(re.split(r"[\s,!?.]+", norm))
    if tokens & _GREETING_TOKENS:
        return True
    if len(norm.split()) <= 4 and any(g in norm for g in _GREETING_TOKENS):
        return True
    return False


def is_identity_question(text: str) -> bool:
    norm = normalize(text)
    return any(re.search(pat, norm) for pat in _IDENTITY_PATTERNS)


def extract_contact_email(text: str) -> Optional[str]:
    m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    return m.group(0) if m else None


def extract_contact_phone(text: str) -> Optional[str]:
    m = re.search(r"\b(\+?\d[\d\s\-]{7,}\d)\b", text)
    if m:
        candidate = re.sub(r"[\s\-]", "", m.group(1))
        if len(candidate) >= 8:
            return candidate
    return None


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


@dataclass
class BaseConversationState(ABC):
    """Universal conversation state — every business has these fields.

    Subclass this for each client and implement the three abstract methods.
    """

    # Universal contact fields
    contact_name: str = ""
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    # Universal funnel tracking
    etapa_funnel: str = "discovery"
    asked_pricing: bool = False
    requested_next_step: bool = False  # demo, appointment, quote, escalation, etc.

    @abstractmethod
    def apply_user_turn(self, text: str) -> None:
        """Update state deterministically from a single user message. No LLM calls."""

    @abstractmethod
    def choose_route(self) -> str:
        """Return the specialist route name: 'discovery', 'qualification', etc."""

    @abstractmethod
    def summary_block(self, **links: str) -> str:
        """Build the state block injected into the system prompt."""
