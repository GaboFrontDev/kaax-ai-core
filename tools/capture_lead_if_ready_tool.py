"""Tool to capture lead data when the conversation is ready for commercial handoff.

Called when contact data (email/phone) appears in user text, or when the user
explicitly requests the next commercial step (demo, pricing, etc.).

If WHATSAPP_NOTIFY_TO is set, sends a WhatsApp notification to that number
whenever a lead with contact data or explicit commercial intent is detected.
"""

from __future__ import annotations

import logging
import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from settings import (
    DEMO_LINK,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_PHONE_NUMBER_ID,
    WHATSAPP_NOTIFY_TO,
)

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(\+?\d[\d\s\-]{7,}\d)\b")


def _build_notification(
    contact_email: str | None,
    contact_phone: str | None,
    requested_demo: bool,
    asked_pricing: bool,
    next_action: str,
    user_text: str,
) -> str:
    lines = ["🔔 *Nuevo lead capturado — Kaax AI*"]
    if contact_email:
        lines.append(f"📧 Email: {contact_email}")
    if contact_phone:
        lines.append(f"📱 Teléfono: {contact_phone}")
    if requested_demo:
        lines.append("✅ Solicitó demo")
    if asked_pricing:
        lines.append("💰 Preguntó por precios/planes")
    lines.append(f"➡️ Acción: {next_action}")
    if user_text:
        snippet = user_text[:120] + ("…" if len(user_text) > 120 else "")
        lines.append(f'💬 Último mensaje: "{snippet}"')
    return "\n".join(lines)


async def _send_demo_link(phone: str) -> None:
    """Send the demo link via WhatsApp to a voice caller."""
    if not WHATSAPP_META_ACCESS_TOKEN or not WHATSAPP_META_PHONE_NUMBER_ID:
        logger.warning("capture_lead: cannot send demo link, Meta credentials missing")
        return
    try:
        from infra.whatsapp_meta.client import send_meta_text_message

        message = f"¡Hola! Aquí está el link para agendar tu demo con Kaax AI:\n{DEMO_LINK}"
        await send_meta_text_message(
            api_version=WHATSAPP_META_API_VERSION,
            phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
            access_token=WHATSAPP_META_ACCESS_TOKEN,
            to=phone,
            text=message,
        )
        logger.info("Demo link sent via WhatsApp to %s", phone)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to send demo link to %s: %s", phone, exc)


async def _notify(message: str) -> None:
    """Send a WhatsApp notification to WHATSAPP_NOTIFY_TO. Silently skips if not configured."""
    if not WHATSAPP_NOTIFY_TO:
        return
    if not WHATSAPP_META_ACCESS_TOKEN or not WHATSAPP_META_PHONE_NUMBER_ID:
        logger.warning("capture_lead: WHATSAPP_NOTIFY_TO set but Meta credentials missing")
        return

    try:
        from infra.whatsapp_meta.client import send_meta_text_message

        await send_meta_text_message(
            api_version=WHATSAPP_META_API_VERSION,
            phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
            access_token=WHATSAPP_META_ACCESS_TOKEN,
            to=WHATSAPP_NOTIFY_TO,
            text=message,
        )
        logger.info("Lead notification sent to %s", WHATSAPP_NOTIFY_TO)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Failed to send lead notification: %s", exc)


class CaptureLeadInput(BaseModel):
    user_text: str = Field(..., description="Latest user message text.")
    contact_email: str | None = Field(default=None, description="Detected email address.")
    contact_phone: str | None = Field(default=None, description="Detected phone number.")
    requested_demo: bool = Field(default=False, description="User explicitly requested a demo.")
    asked_pricing: bool = Field(default=False, description="User asked about pricing.")
    caller_phone: str | None = Field(
        default=None,
        description="Phone number of the caller on a voice call. Pass this when handling a voice call so the demo link can be sent via WhatsApp.",
    )


@tool(args_schema=CaptureLeadInput)
async def capture_lead_if_ready_tool(
    user_text: str,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    requested_demo: bool = False,
    asked_pricing: bool = False,
    caller_phone: str | None = None,
) -> dict:
    """Capture lead data when the conversation is ready for commercial handoff.

    Call this when:
    - Contact data (email or phone) appears in the user message.
    - User explicitly requests the next commercial step.

    Returns capture status and recommended next action.
    """
    # Auto-detect contact info from user_text if not passed explicitly
    if contact_email is None:
        m = _EMAIL_RE.search(user_text)
        if m:
            contact_email = m.group(0)

    if contact_phone is None:
        m = _PHONE_RE.search(user_text)
        if m:
            candidate = re.sub(r"[\s\-]", "", m.group(1))
            if len(candidate) >= 8:
                contact_phone = candidate

    has_contact = bool(contact_email or contact_phone)
    is_ready = has_contact or requested_demo or asked_pricing

    if not is_ready:
        next_action = "not_ready"
    elif has_contact:
        next_action = "handoff_to_sales"
    elif requested_demo:
        next_action = "send_demo_link"
    elif asked_pricing:
        next_action = "send_pricing_link"
    else:
        next_action = "request_contact"

    if is_ready:
        logger.info(
            "Lead capture triggered | has_email=%s has_phone=%s demo=%s pricing=%s action=%s",
            bool(contact_email),
            bool(contact_phone),
            requested_demo,
            asked_pricing,
            next_action,
        )
        notification = _build_notification(
            contact_email, contact_phone, requested_demo, asked_pricing, next_action, user_text
        )
        await _notify(notification)

        # Voice call: send demo link directly to caller via WhatsApp
        if requested_demo and caller_phone and DEMO_LINK:
            await _send_demo_link(caller_phone)

    return {
        "captured": is_ready,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "has_contact_data": has_contact,
        "next_action": next_action,
    }
