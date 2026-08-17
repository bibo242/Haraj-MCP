"""Load and validate the Haraj JWT from .env."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass


@dataclass
class HarajAuth:
    jwt: str
    last_request_id: str

    def authorization_header(self) -> str:
        return f"Bearer {self.jwt}"


class AuthError(RuntimeError):
    """Raised when auth is missing, malformed, or expired."""


def _decode_jwt_payload(jwt: str) -> dict:
    parts = jwt.split(".")
    if len(parts) != 3:
        raise AuthError(
            "HARAJ_JWT does not look like a JWT (expected 3 dot-separated parts)."
        )
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception as exc:
        raise AuthError(f"Could not decode JWT payload: {exc}") from exc


def load_auth(jwt: str, last_request_id: str) -> HarajAuth:
    if not jwt or jwt.startswith("eyJ....paste"):
        raise AuthError(
            "HARAJ_JWT is not set. Edit your .env and paste the Bearer token from "
            "Chrome DevTools > Network > any GraphQL request > authorization header."
        )
    if not last_request_id or last_request_id.startswith("0000000"):
        raise AuthError(
            "LAST_REQUEST_ID is not set. Edit your .env and paste the lastRequestId "
            "header value from the same GraphQL request."
        )

    payload = _decode_jwt_payload(jwt)
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        now = time.time()
        if exp < now:
            raise AuthError(
                f"JWT expired at {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(exp))} UTC. "
                "Re-login to haraj.com.sa and refresh HARAJ_JWT + LAST_REQUEST_ID."
            )
    return HarajAuth(jwt=jwt, last_request_id=last_request_id)
