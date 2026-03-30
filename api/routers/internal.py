"""Internal admin endpoints — protected by bearer token."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth import validate_token

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/digest/trigger")
async def trigger_digest(_token: str = Depends(validate_token)):
    """Manually trigger the conversation digest and send it to WHATSAPP_NOTIFY_TO."""
    from infra.follow_up.digest_scheduler import _run_once
    await _run_once()
    return {"status": "ok", "message": "Digest sent"}
