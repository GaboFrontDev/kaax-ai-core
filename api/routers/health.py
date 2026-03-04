"""Health endpoint for core API."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "ok", "message": "core service is running"}


@router.get("/health/live")
async def live_check():
    return {"status": "ok", "message": "core service is running"}
