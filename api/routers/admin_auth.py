"""Admin authentication via WhatsApp OTP."""

from __future__ import annotations

import random
import string
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from settings import (
    ADMIN_JWT_EXPIRE_HOURS,
    ADMIN_JWT_SECRET,
    ADMIN_PHONES,
    WHATSAPP_META_ACCESS_TOKEN,
    WHATSAPP_META_API_VERSION,
    WHATSAPP_META_PHONE_NUMBER_ID,
)

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])

_OTP_EXPIRE_MINUTES = 5


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


async def _save_otp(phone: str, code: str) -> None:
    import psycopg
    from sql_utilities import get_database_url
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_OTP_EXPIRE_MINUTES)
    async with await psycopg.AsyncConnection.connect(get_database_url()) as conn:
        await conn.execute(
            "INSERT INTO admin_otps (phone, code, expires_at) VALUES (%s, %s, %s)",
            (phone, code, expires_at),
        )


async def _verify_otp(phone: str, code: str) -> bool:
    import psycopg
    from sql_utilities import get_database_url
    now = datetime.now(timezone.utc)
    async with await psycopg.AsyncConnection.connect(get_database_url()) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT id FROM admin_otps
                WHERE phone = %s AND code = %s AND used = FALSE AND expires_at > %s
                ORDER BY created_at DESC LIMIT 1
                """,
                (phone, code, now),
            )
            row = await cur.fetchone()
            if not row:
                return False
            await conn.execute("UPDATE admin_otps SET used = TRUE WHERE id = %s", (row[0],))
            return True


def _issue_token(phone: str) -> str:
    payload = {
        "sub": phone,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ADMIN_JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, ADMIN_JWT_SECRET, algorithm="HS256")


@router.get("/admins")
async def list_admins():
    """Returns masked phone list for the login UI."""
    return [{"phone": p, "label": f"****{p[-4:]}"} for p in ADMIN_PHONES]


class RequestOTPBody(BaseModel):
    phone: str


class VerifyOTPBody(BaseModel):
    phone: str
    code: str


@router.post("/request-otp")
async def request_otp(body: RequestOTPBody):
    if body.phone not in ADMIN_PHONES:
        raise HTTPException(status_code=403, detail="Número no autorizado")

    code = _generate_otp()
    await _save_otp(body.phone, code)

    if WHATSAPP_META_ACCESS_TOKEN and WHATSAPP_META_PHONE_NUMBER_ID:
        from infra.whatsapp_meta.client import send_meta_text_message
        await send_meta_text_message(
            api_version=WHATSAPP_META_API_VERSION,
            phone_number_id=WHATSAPP_META_PHONE_NUMBER_ID,
            access_token=WHATSAPP_META_ACCESS_TOKEN,
            to=body.phone,
            text=f"Tu código de acceso al panel de LW Mobiliario es: *{code}*\nExpira en {_OTP_EXPIRE_MINUTES} minutos.",
        )

    return {"ok": True}


@router.post("/verify-otp")
async def verify_otp(body: VerifyOTPBody):
    if body.phone not in ADMIN_PHONES:
        raise HTTPException(status_code=403, detail="Número no autorizado")

    valid = await _verify_otp(body.phone, body.code)
    if not valid:
        raise HTTPException(status_code=401, detail="Código inválido o expirado")

    token = _issue_token(body.phone)
    return {"token": token}
