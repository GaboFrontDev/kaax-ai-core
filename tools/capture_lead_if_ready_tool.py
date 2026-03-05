"""Tool to capture lead data when the conversation is ready for commercial handoff.

Called when contact data (email/phone) appears in user text, or when the user
explicitly requests the next commercial step (demo, pricing, etc.).
"""

from __future__ import annotations

import logging
import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"\b(\+?\d[\d\s\-]{7,}\d)\b")


class CaptureLeadInput(BaseModel):
    user_text: str = Field(..., description="Latest user message text.")
    contact_email: str | None = Field(default=None, description="Detected email address.")
    contact_phone: str | None = Field(default=None, description="Detected phone number.")
    requested_demo: bool = Field(default=False, description="User explicitly requested a demo.")
    asked_pricing: bool = Field(default=False, description="User asked about pricing.")


@tool(args_schema=CaptureLeadInput)
async def capture_lead_if_ready_tool(
    user_text: str,
    contact_email: str | None = None,
    contact_phone: str | None = None,
    requested_demo: bool = False,
    asked_pricing: bool = False,
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

    if is_ready:
        logger.info(
            "Lead capture triggered | has_email=%s has_phone=%s demo=%s pricing=%s",
            bool(contact_email),
            bool(contact_phone),
            requested_demo,
            asked_pricing,
        )

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

    return {
        "captured": is_ready,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "has_contact_data": has_contact,
        "next_action": next_action,
    }
