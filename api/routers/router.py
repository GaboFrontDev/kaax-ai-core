"""Main router for core API."""

from __future__ import annotations

from fastapi import APIRouter

from api.routers import assist, health, twilio_voice, whatsapp_meta

router = APIRouter()
router.include_router(health.router)
router.include_router(assist.router)
router.include_router(whatsapp_meta.router)
router.include_router(twilio_voice.router)
