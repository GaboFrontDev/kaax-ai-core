"""Internal admin endpoints — protected by bearer token."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.auth import validate_token

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/digest/trigger")
async def trigger_digest(
    lookback_hours: int = 0,
    _token: str = Depends(validate_token),
):
    """Manually trigger the conversation digest and send it to WHATSAPP_NOTIFY_TO.

    Pass lookback_hours to override the default window (0 = use configured default).
    """
    from infra.follow_up.digest_scheduler import _run_once
    await _run_once(lookback_hours_override=lookback_hours or None)
    return {"status": "ok", "message": "Digest sent"}
