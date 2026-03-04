"""Main router for core API."""

from __future__ import annotations

from fastapi import APIRouter

from api.routers import assist, health, whatsapp_meta

router = APIRouter()
router.include_router(health.router)
router.include_router(assist.router)
router.include_router(whatsapp_meta.router)
