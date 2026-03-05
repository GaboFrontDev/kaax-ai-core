"""Deterministic ConversationState for Kaax AI multi-agent supervisor.

All extraction is regex/keyword-based — no LLM calls, no side effects.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal, Optional


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


# ---------------------------------------------------------------------------
# Greeting detector
# ---------------------------------------------------------------------------

_GREETING_TOKENS = frozenset(
    [
        "hola",
        "buenas",
        "hey",
        "hi",
        "hello",
        "saludos",
        "buenos",
        "buen",
        "buenas",
        "ola",
    ]
)
_GREETING_TRIGGER_WORDS = frozenset(["ai", "kaax"])


def is_greeting(text: str) -> bool:
    """Return True if the message is a greeting or AI trigger."""
    norm = normalize(text)
    tokens = set(re.split(r"[\s,!?.]+", norm))
    if tokens & _GREETING_TOKENS:
        return True
    if tokens & _GREETING_TRIGGER_WORDS:
        return True
    # Short message containing a greeting token
    if len(norm.split()) <= 4 and any(g in norm for g in _GREETING_TOKENS):
        return True
    return False


# ---------------------------------------------------------------------------
# Identity question detector
# ---------------------------------------------------------------------------

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


def is_identity_question(text: str) -> bool:
    """Return True if user is asking who/what the agent is."""
    norm = normalize(text)
    return any(re.search(pat, norm) for pat in _IDENTITY_PATTERNS)


# ---------------------------------------------------------------------------
# Channel extractor
# ---------------------------------------------------------------------------

_CHANNEL_KEYWORDS: dict[str, str] = {
    "whatsapp": "whatsapp",
    "wha": "whatsapp",
    "wsp": "whatsapp",
    "instagram": "instagram",
    "ig": "instagram",
    "insta": "instagram",
    "facebook": "facebook",
    "fb": "facebook",
    "web": "web",
    "pagina": "web",
    "sitio": "web",
    "website": "web",
    "chat": "web",
}


def extract_channel(text: str) -> Optional[str]:
    """Extract the primary channel from user text."""
    norm = normalize(text)
    for kw, channel in _CHANNEL_KEYWORDS.items():
        if re.search(r"\b" + re.escape(kw) + r"\b", norm):
            return channel
    return None


# ---------------------------------------------------------------------------
# Volume extractor
# ---------------------------------------------------------------------------

_VOLUME_RANGE_PATTERNS: list[tuple[re.Pattern, str, int]] = [
    (re.compile(r"menos\s+de\s+20|<\s*20"), "menos de 20", 10),
    (re.compile(r"\b20\s+a\s+100\b"), "20 a 100", 60),
    (re.compile(r"\b100\s+a\s+300\b"), "100 a 300", 200),
    (re.compile(r"mas\s+de\s+300|>\s*300|\+\s*300|\b300\+"), "mas de 300", 400),
]

# Pure single-digit menu options (1–4) standing alone are not volume answers
_MENU_ONLY_PATTERN = re.compile(r"^\s*[1-4]\s*$")


def extract_volume(
    text: str,
    past_menu_phase: bool = False,
) -> tuple[Optional[int], Optional[str]]:
    """Return (representative_int, range_label) or (None, None).

    Explicit range labels take priority.

    Args:
        past_menu_phase: When True, the goal-selection menu has already been
            completed (negocio_tipo is known), so bare single digits 1-4 should
            be treated as low-volume answers, not menu selections.
    """
    norm = normalize(text)

    # Only filter 1-4 as menu selections while the goal menu is still active.
    if not past_menu_phase and _MENU_ONLY_PATTERN.match(norm):
        return None, None

    # Explicit range labels
    for pattern, label, representative_int in _VOLUME_RANGE_PATTERNS:
        if pattern.search(norm):
            return representative_int, label

    # Extract integers from text.
    # Note: bare single-digit menu options are already rejected by _MENU_ONLY_PATTERN above,
    # so any number found here is valid context (e.g. "2 mensajes", "recibo 2 al dia").
    numbers = re.findall(r"\b(\d+)\b", norm)
    if not numbers:
        return None, None

    val = int(numbers[0])
    if val < 20:
        return val, "menos de 20"
    elif val <= 100:
        return val, "20 a 100"
    elif val <= 300:
        return val, "100 a 300"
    else:
        return val, "mas de 300"


# ---------------------------------------------------------------------------
# Intent extractor
# ---------------------------------------------------------------------------

_INTENT_ALTA_KEYWORDS = frozenset(
    [
        "precio",
        "precios",
        "plan",
        "planes",
        "cuanto cuesta",
        "costo",
        "quiero comprar",
        "quiero contratar",
        "contratar",
        "comprar",
        "lista para",
        "listo para",
        "ya quiero",
        "necesito ya",
        "demo",
        "agendar",
        "agenda",
        "ver demo",
        "ver planes",
        "implementar",
        "implementacion",
        "cuando empezamos",
    ]
)

_INTENT_MEDIA_KEYWORDS = frozenset(
    [
        "me interesa",
        "interesante",
        "me llama la atencion",
        "suena bien",
        "podria ser",
        "lo estoy pensando",
        "estoy evaluando",
        "evaluando",
        "quizas",
        "talvez",
        "tal vez",
        "posiblemente",
        "probablemente",
        "mas informacion",
        "mas info",
        "cuentame mas",
        "quisiera saber",
        "me gustaria saber",
    ]
)


def extract_intent(text: str) -> Optional[Literal["baja", "media", "alta"]]:
    """Return the highest detected purchase intent, or None if unclear."""
    norm = normalize(text)
    for kw in _INTENT_ALTA_KEYWORDS:
        if kw in norm:
            return "alta"
    for kw in _INTENT_MEDIA_KEYWORDS:
        if kw in norm:
            return "media"
    return None


# ---------------------------------------------------------------------------
# Product/service extractor
# ---------------------------------------------------------------------------

_PRODUCT_BLACKLIST_PATTERNS = [
    r"^\s*\d+\s*$",  # pure number
    r"\bcuanto\b",  # quantity question
    r"\bmenoraje\b|\bmensajes\b",  # volume question
    r"\binstagram\b|\bwhatsapp\b|\bfacebook\b|\bweb\b",  # channels
    r"^(hola|hey|hi|buenas|saludos)",  # greetings
    r"\?$",  # ends in question
    r"^(si|no|ok|claro|gracias|perfecto|entendido|dale|listo|okay)$",  # ack
    r"\brecibo\b.*\bmensajes\b|\bmensajes\b.*\brecibo\b",  # volume sentences
]


def extract_product_service(text: str) -> Optional[str]:
    """Lightweight heuristic: short noun phrase from non-question statements."""
    norm = normalize(text)
    for pat in _PRODUCT_BLACKLIST_PATTERNS:
        if re.search(pat, norm):
            return None
    # Skip volume-like sentences
    if re.search(r"\b\d+\s*(mensajes|al\s+dia|por\s+dia)\b", norm):
        return None
    words = norm.split()
    if len(words) < 2:
        return None
    # Return first 6 words of original text as the product snippet
    original_words = text.strip().split()
    return " ".join(original_words[:6])


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

VolumenRango = Literal["menos de 20", "20 a 100", "100 a 300", "mas de 300"]
IntencioCompra = Literal["baja", "media", "alta"]

_INTENT_PRIORITY: dict[str, int] = {"baja": 0, "media": 1, "alta": 2}


# ---------------------------------------------------------------------------
# ConversationState dataclass
# ---------------------------------------------------------------------------


@dataclass
class ConversationState:
    """Deterministic state extracted from user turns — no LLM required."""

    etapa_funnel: str = "primer_contacto"
    negocio_tipo: Optional[str] = None  # ventas / atencion / citas / marketing
    producto_servicio: Optional[str] = None
    volumen_mensajes_valor_aprox: Optional[int] = None
    volumen_mensajes_rango: Optional[VolumenRango] = None
    canal_principal: Optional[str] = None
    intencion_compra: IntencioCompra = "baja"
    requested_demo: bool = False
    asked_pricing: bool = False
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    # internal: track goal menu selection raw text
    _negocio_raw: Optional[str] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def volume_fit(self) -> Literal["fuerte", "en_desarrollo", "desconocido"]:
        if self.volumen_mensajes_rango is None:
            return "desconocido"
        if self.volumen_mensajes_rango == "menos de 20":
            return "en_desarrollo"
        return "fuerte"

    def apply_user_turn(self, text: str) -> None:
        """Update state fields deterministically from a single user message."""
        norm = normalize(text)

        # Capture the phase flag BEFORE any mutations so that the turn which
        # sets negocio_tipo does not also treat its own digit as a volume answer.
        was_past_menu_phase = self.negocio_tipo is not None

        # Goal-menu selection (1–4) only if negocio_tipo not yet set
        if self.negocio_tipo is None:
            _goal_map = {
                "1": "ventas",
                "2": "atencion",
                "3": "citas",
                "4": "marketing",
                "ventas": "ventas",
                "atencion": "atencion",
                "citas": "citas",
                "marketing": "marketing",
                "leads": "marketing",
            }
            for token, goal in _goal_map.items():
                if re.search(r"\b" + re.escape(token) + r"\b", norm):
                    self.negocio_tipo = goal
                    break

        # Channel
        if self.canal_principal is None:
            ch = extract_channel(text)
            if ch:
                self.canal_principal = ch

        # Volume — disable the menu-option filter once negocio_tipo was already known
        # before this turn, so bare answers like "3" or "5" are captured as volume.
        if self.volumen_mensajes_rango is None:
            val, rng = extract_volume(text, past_menu_phase=was_past_menu_phase)
            if rng:
                self.volumen_mensajes_valor_aprox = val
                self.volumen_mensajes_rango = rng  # type: ignore[assignment]

        # Intent — only upgrade, never downgrade
        intent = extract_intent(text)
        if intent and _INTENT_PRIORITY.get(intent, 0) > _INTENT_PRIORITY.get(
            self.intencion_compra, 0
        ):
            self.intencion_compra = intent

        # Product/service
        if self.producto_servicio is None:
            ps = extract_product_service(text)
            if ps:
                self.producto_servicio = ps

        # Demo request flag
        if not self.requested_demo:
            if re.search(r"\bdemo\b|\bagendar\b|\bagenda\b|\bver\s+demo\b", norm):
                self.requested_demo = True

        # Pricing request flag
        if not self.asked_pricing:
            if re.search(
                r"\bprecio(s)?\b|\bplan(es)?\b|\bcuanto\s+cuesta\b|\bcosto\b|\bver\s+planes\b",
                norm,
            ):
                self.asked_pricing = True

        # Email
        if self.contact_email is None:
            m = re.search(
                r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text
            )
            if m:
                self.contact_email = m.group(0)

        # Phone (8+ digits)
        if self.contact_phone is None:
            m = re.search(r"\b(\+?\d[\d\s\-]{7,}\d)\b", text)
            if m:
                candidate = re.sub(r"[\s\-]", "", m.group(1))
                if len(candidate) >= 8:
                    self.contact_phone = candidate

        # Update stage
        self.etapa_funnel = infer_stage(self)


# ---------------------------------------------------------------------------
# Stage inference
# ---------------------------------------------------------------------------


def missing_fields(state: ConversationState) -> list[str]:
    """Return the ordered list of fields still needed for full qualification."""
    missing: list[str] = []
    if state.producto_servicio is None:
        missing.append("producto_servicio")
    if state.volumen_mensajes_rango is None:
        missing.append("volumen_mensajes_rango")
    if state.canal_principal is None:
        missing.append("canal_principal")
    return missing


def infer_stage(state: ConversationState) -> str:
    """Deterministic funnel stage from state fields."""
    if state.negocio_tipo is None:
        return "primer_contacto"
    if missing_fields(state):
        return "diagnostico"
    # All fields present
    vf = state.volume_fit()
    is_hot = state.intencion_compra == "alta" or state.requested_demo or state.asked_pricing
    if is_hot:
        if vf == "fuerte":
            return "cierre"
        if vf == "en_desarrollo" and not state.requested_demo:
            return "nutricion"
        return "cierre"
    return "calificacion"


def choose_specialist_route(
    state: ConversationState,
    force_knowledge: bool = False,
) -> Literal["discovery", "qualification", "capture", "knowledge"]:
    """Deterministic route with hard guardrails.

    Guardrail: en_desarrollo + no explicit demo/pricing request → never capture.
    """
    if force_knowledge or state.asked_pricing:
        return "knowledge"

    stage = infer_stage(state)
    vf = state.volume_fit()

    # Hard guardrail (belt-and-suspenders)
    capture_blocked = (
        vf == "en_desarrollo"
        and not state.requested_demo
        and not state.asked_pricing
    )

    if stage in ("primer_contacto", "diagnostico"):
        return "discovery"

    if stage == "cierre":
        if capture_blocked:
            return "qualification"
        return "capture"

    if stage in ("nutricion", "calificacion"):
        return "qualification"

    return "discovery"


# ---------------------------------------------------------------------------
# State summary block — injected into system prompt
# ---------------------------------------------------------------------------


def state_summary_block(
    state: ConversationState,
    demo_link: str,
    pricing_link: str,
) -> str:
    """Build a compact state block for injection into the system prompt.

    Links are included only when semantically appropriate, never hardcoded.
    """
    vf = state.volume_fit()
    missing = missing_fields(state)

    lines = [
        "=== ConversationState ===",
        f"etapa_funnel: {state.etapa_funnel}",
        f"negocio_tipo: {state.negocio_tipo or '—'}",
        f"producto_servicio: {state.producto_servicio or '—'}",
        f"volumen_rango: {state.volumen_mensajes_rango or '—'} ({vf})",
        f"canal_principal: {state.canal_principal or '—'}",
        f"intencion_compra: {state.intencion_compra}",
        f"requested_demo: {state.requested_demo}",
        f"asked_pricing: {state.asked_pricing}",
        f"contact_email: {state.contact_email or '—'}",
        f"contact_phone: {state.contact_phone or '—'}",
        f"missing_fields: {', '.join(missing) if missing else 'none'}",
    ]

    # Inject links only when contextually appropriate
    if state.requested_demo or (vf == "fuerte" and state.intencion_compra == "alta"):
        lines.append(f"DEMO_LINK: {demo_link}")
    if state.asked_pricing:
        lines.append(f"PRICING_LINK: {pricing_link}")

    lines.append("=========================")
    return "\n".join(lines)
