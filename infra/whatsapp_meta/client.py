from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def send_typing_action(
    *,
    api_version: str,
    phone_number_id: str,
    access_token: str,
    to: str,
) -> None:
    """Send a typing indicator to the user. Best-effort — errors are logged and ignored."""
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "chat_action",
        "chat_action": "typing_on",
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.debug("typing_indicator_failed: %s", exc)


async def send_meta_text_message(
    *,
    api_version: str,
    phone_number_id: str,
    access_token: str,
    to: str,
    text: str,
) -> dict[str, object]:
    body = (text or "").strip()
    if len(body) > 4096:
        body = f"{body[:4093]}..."

    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body or "Mensaje recibido."},
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return dict(response.json())
