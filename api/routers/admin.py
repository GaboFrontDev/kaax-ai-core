"""Admin endpoints — conversation viewer and handoff management."""

from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from settings import (
    ADMIN_JWT_SECRET,
    ADMIN_PHONES,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_PHONE_NUMBER_ID,
)
from infra.follow_up.db import (
    HANDOFF_RELEASED_CONTROL,
    CONTROL_MESSAGE_PREFIX,
    save_control_message,
    set_handoff_requested,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])
_bearer = HTTPBearer()


def _require_admin(credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)]) -> str:
    try:
        payload = jwt.decode(credentials.credentials, ADMIN_JWT_SECRET, algorithms=["HS256"])
        phone = payload.get("sub", "")
        if phone not in ADMIN_PHONES:
            raise HTTPException(status_code=403, detail="No autorizado")
        return phone
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sesión expirada")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


@router.get("/conversations")
async def list_conversations(
    handoff_only: bool = False,
    limit: int = 50,
    _admin: str = Depends(_require_admin),
):
    import psycopg
    from sql_utilities import get_database_url
    where = "WHERE handoff_requested = TRUE" if handoff_only else ""
    async with await psycopg.AsyncConnection.connect(get_database_url()) as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            await cur.execute(
                f"""
                SELECT thread_id, channel, phone_number, contact_name,
                       handoff_requested, last_message_at, created_at
                FROM conversations
                {where}
                ORDER BY last_message_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    return rows


@router.get("/conversations/{thread_id}/messages")
async def get_messages(thread_id: str, _admin: str = Depends(_require_admin)):
    import psycopg
    from sql_utilities import get_database_url
    async with await psycopg.AsyncConnection.connect(get_database_url()) as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            await cur.execute(
                """
                SELECT id, role, content, created_at
                FROM conversation_messages
                WHERE thread_id = %s
                  AND content NOT LIKE %s
                ORDER BY created_at ASC
                """,
                (thread_id, f"{CONTROL_MESSAGE_PREFIX}%"),
            )
            rows = await cur.fetchall()
    return rows


class ReplyBody(BaseModel):
    text: str


class HandoffBody(BaseModel):
    active: bool


@router.post("/conversations/{thread_id}/reply")
async def reply(thread_id: str, body: ReplyBody, _admin: str = Depends(_require_admin)):
    import psycopg
    from sql_utilities import get_database_url
    async with await psycopg.AsyncConnection.connect(get_database_url()) as conn:
        async with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            await cur.execute("SELECT phone_number FROM conversations WHERE thread_id = %s", (thread_id,))
            row = await cur.fetchone()
    if not row or not row["phone_number"]:
        raise HTTPException(status_code=404, detail="Conversación sin número de teléfono")

    if not WHATSAPP_META_ACCESS_TOKEN or not WHATSAPP_META_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WhatsApp no configurado")

    from infra.whatsapp_meta.client import send_meta_text_message
    from infra.follow_up.db import save_message
    await send_meta_text_message(
        api_version=WHATSAPP_META_API_VERSION,
        phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
        access_token=WHATSAPP_META_ACCESS_TOKEN,
        to=row["phone_number"],
        text=body.text,
    )
    await save_message(thread_id, "admin", body.text)
    return {"ok": True}


@router.patch("/conversations/{thread_id}/handoff")
async def set_handoff(thread_id: str, body: HandoffBody, _admin: str = Depends(_require_admin)):
    changed = await set_handoff_requested(thread_id, body.active)
    if changed and not body.active:
        await save_control_message(thread_id, HANDOFF_RELEASED_CONTROL)
    return {"ok": True, "handoff_requested": body.active}
