"""Twilio webhook signature validation."""

from __future__ import annotations

import base64
import hashlib
import hmac


def validate_twilio_signature(
    auth_token: str,
    request_url: str,
    post_params: dict[str, str],
    signature: str,
) -> bool:
    """
    Validate the X-Twilio-Signature header.

    Twilio signs requests by concatenating the full URL with all POST
    parameters sorted alphabetically (key immediately followed by value,
    no separators), then computing HMAC-SHA1 with the auth token and
    base64-encoding the result.
    """
    s = request_url
    for key in sorted(post_params.keys()):
        s += key + (post_params[key] or "")

    expected = base64.b64encode(
        hmac.new(
            auth_token.encode("utf-8"),
            s.encode("utf-8"),
            hashlib.sha1,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(expected, signature)
