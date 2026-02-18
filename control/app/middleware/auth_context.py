"""Lightweight auth-context middleware.

Runs early in the middleware stack to decode JWT identity and attach it
to ``request.state``.  Does **not** enforce authentication — that remains
the job of FastAPI dependencies (``get_current_user``, ``require_role``).

Purposes
--------
1. Populate ``request.state.user_identity`` (username / user_id) so the
   audit middleware can log *who* performed a mutation without duplicating
   the JWT decode logic.
2. Detect **expired** tokens and set the ``X-Token-Expired: true``
   response header.  This gives the frontend a deterministic signal to
   clear stale cookies / local-storage tokens and redirect to ``/login``
   without entering a retry loop.
"""
import logging
from dataclasses import dataclass
from typing import Optional

from fastapi import Request, Response
from jose import JWTError, ExpiredSignatureError, jwt
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class UserIdentity:
    """Minimal identity extracted from a JWT (no DB lookup)."""

    username: str
    is_expired: bool = False


def _extract_token(request: Request) -> Optional[str]:
    """Return the raw JWT from Authorization header or ?token= query param."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # WebSocket-style query param fallback
    return request.query_params.get("token")


def _decode_identity(token: str) -> UserIdentity:
    """Decode a JWT and return identity.  Never raises."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        username = payload.get("sub", "")
        return UserIdentity(username=username, is_expired=False)
    except ExpiredSignatureError:
        # Token structure is valid but expired — decode without verification
        # to get the username for audit purposes.
        try:
            payload = jwt.decode(
                token,
                settings.secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"verify_exp": False},
            )
            return UserIdentity(
                username=payload.get("sub", ""),
                is_expired=True,
            )
        except JWTError:
            return UserIdentity(username="", is_expired=True)
    except JWTError:
        return UserIdentity(username="", is_expired=False)


class AuthContextMiddleware(BaseHTTPMiddleware):
    """Attach JWT identity to request.state and flag expired tokens."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = _extract_token(request)
        identity: Optional[UserIdentity] = None

        if token:
            identity = _decode_identity(token)

        # Attach to request.state so audit middleware (and others) can use it.
        request.state.user_identity = identity

        response = await call_next(request)

        # If the token was expired, tag the response so the frontend knows
        # to clear stale credentials and redirect to login.
        if identity and identity.is_expired:
            response.headers["X-Token-Expired"] = "true"

        return response
