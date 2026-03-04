"""Main router for core API."""

from __future__ import annotations

from fastapi import APIRouter

from api.routers import assist, health

router = APIRouter()
router.include_router(health.router)
router.include_router(assist.router)
