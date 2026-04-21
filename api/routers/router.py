"""Main router for core API."""

from __future__ import annotations

from fastapi import APIRouter

from api.routers import admin, admin_auth, assist, health, internal, twilio_voice, whatsapp_calls, whatsapp_meta

router = APIRouter()
router.include_router(health.router)
router.include_router(assist.router)
router.include_router(whatsapp_meta.router)
router.include_router(whatsapp_calls.router)
router.include_router(twilio_voice.router)
router.include_router(internal.router)
router.include_router(admin_auth.router)
router.include_router(admin.router)
