"""Auth helpers for the haraj MCP server.

Reads HARAJ_JWT and LAST_REQUEST_ID from a .env file next to the server
(or in the directory the MCP client sets via cwd).

The MCP server doesn't read the haraj.com.sa login itself — it just
forwards whatever JWT the user put in .env. Tokens expire every ~10 days;
the user pastes fresh ones in Chrome DevTools and restarts.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from pathlib import Path


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
        raise AuthError("JWT does not look like a 3-part token.")
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
    except Exception as exc:
        raise AuthError(f"Could not decode JWT payload: {exc}") from exc


def load_auth_from_env(env_path: Path | str | None = None) -> HarajAuth:
    """Load HARAJ_JWT and LAST_REQUEST_ID from .env.

    If `env_path` is None, looks in (in order):
      1) cwd of the server process
      2) the haraj-mcp package directory
      3) the user's home directory
    """
    if env_path is None:
        candidates = [
            Path.cwd() / ".env",
            Path(__file__).resolve().parent.parent.parent / ".env",
            Path.home() / ".env",
        ]
    else:
        candidates = [Path(env_path)]

    raw: dict[str, str] = {}
    for path in candidates:
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                raw[key.strip()] = value.strip().strip('"').strip("'")
            break

    jwt = raw.get("HARAJ_JWT", "")
    last_req = raw.get("LAST_REQUEST_ID", "")

    if not jwt or jwt.startswith("eyJ....paste"):
        raise AuthError(
            "HARAJ_JWT not set. Paste your Bearer token into .env next to the server."
        )
    if not last_req or last_req.startswith("0000000"):
        raise AuthError(
            "LAST_REQUEST_ID not set. Paste the lastRequestId header value into .env."
        )

    return HarajAuth(jwt=jwt, last_request_id=last_req)


def jwt_status(jwt: str) -> dict:
    """Return a small dict describing the JWT for `check_auth` tool."""
    try:
        payload = _decode_jwt_payload(jwt)
    except AuthError as exc:
        return {"ok": False, "error": str(exc)}

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return {"ok": True, "warning": "no exp claim"}

    now = time.time()
    if exp < now:
        return {
            "ok": False,
            "expired_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(exp)),
            "error": "JWT has expired. Re-login to haraj.com.sa and refresh .env.",
        }

    seconds_left = exp - now
    return {
        "ok": True,
        "expires_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(exp)),
        "seconds_remaining": int(seconds_left),
        "user_id": payload.get("id"),
        "tc": payload.get("tc"),
    }