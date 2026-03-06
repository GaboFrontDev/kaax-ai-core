"""Twilio REST API helpers for mid-call TwiML updates."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_CALLS_URL = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Calls/{call_sid}.json"


async def update_call_twiml(
    account_sid: str,
    auth_token: str,
    call_sid: str,
    twiml: str,
) -> None:
    """
    Update a live Twilio call with new TwiML.

    Used to inject audio mid-call: Twilio stops the current stream,
    plays the TwiML, then reconnects to the stream URL if present.
    """
    url = _CALLS_URL.format(account_sid=account_sid, call_sid=call_sid)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            url,
            auth=(account_sid, auth_token),
            data={"Twiml": twiml},
        )
        resp.raise_for_status()
        logger.info("twilio_rest update_call call_sid=%s status=%d", call_sid, resp.status_code)
