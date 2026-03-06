from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def send_typing_action(
    *,
    api_version: str,
    phone_number_id: str,
    access_token: str,
    message_id: str,
) -> None:
    """Mark message as read and show typing indicator. Best-effort — errors are logged and ignored."""
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
        "typing_indicator": {"type": "text"},
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except Exception as exc:
        logger.debug("typing_indicator_failed: %s", exc)


async def download_media(
    *,
    api_version: str,
    media_id: str,
    access_token: str,
) -> bytes:
    """Download a WhatsApp media file (audio/image/etc) by its media_id.

    Meta flow:
      1. GET /v{api_version}/{media_id} → JSON with {"url": "...", "mime_type": "..."}
      2. GET {url} with Bearer token → raw bytes
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: resolve media URL
        meta_resp = await client.get(
            f"https://graph.facebook.com/{api_version}/{media_id}",
            headers=headers,
        )
        meta_resp.raise_for_status()
        media_url = meta_resp.json()["url"]

        # Step 2: download the actual bytes
        media_resp = await client.get(media_url, headers=headers)
        media_resp.raise_for_status()
        return media_resp.content


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
