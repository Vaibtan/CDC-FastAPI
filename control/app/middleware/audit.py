"""Audit logging middleware for mutation tracking.

Logs POST / PATCH / PUT / DELETE requests to the audit_logs table
after the response is produced.  Read-only methods (GET, HEAD, OPTIONS)
are silently skipped.
"""
import logging
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.database import get_db_context
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

_MUTATING_METHODS = {"POST", "PATCH", "PUT", "DELETE"}


def _extract_resource(path: str) -> tuple[str, str | None]:
    """Derive (resource_type, resource_id) from a request path.

    Examples:
        /api/v1/jobs              -> ("replay_job", None)
        /api/v1/jobs/abc-123      -> ("replay_job", "abc-123")
        /api/v1/jobs/abc/start    -> ("replay_job", "abc")
        /api/v1/auth/register     -> ("auth", None)
    """
    parts = [p for p in path.strip("/").split("/") if p]

    # Skip api/v1 prefix
    if len(parts) >= 2 and parts[0] == "api" and parts[1].startswith("v"):
        parts = parts[2:]

    if not parts:
        return ("unknown", None)

    resource_type = parts[0]  # "jobs", "auth", "events", "health"

    # Normalise plural -> singular for known resources
    if resource_type == "jobs":
        resource_type = "replay_job"

    resource_id = parts[1] if len(parts) >= 2 and resource_type != "auth" else None

    return (resource_type, resource_id)


def _derive_action(
    method: str,
    path: str,
    resource_type: str,
    resource_id: str | None,
) -> str:
    """Return a stable audit action name for the request."""
    parts = [p for p in path.strip("/").split("/") if p]
    if len(parts) >= 2 and parts[0] == "api" and parts[1].startswith("v"):
        parts = parts[2:]

    tail = parts[-1] if parts else method.lower()

    if method == "POST":
        if resource_id and tail in {"start", "pause", "resume", "cancel"}:
            return f"{resource_type}.{tail}"
        if resource_type == "auth":
            return f"auth.{tail}"
        return f"{resource_type}.create"

    if method in {"PATCH", "PUT"}:
        return f"{resource_type}.update"

    if method == "DELETE":
        return f"{resource_type}.delete"

    return f"{resource_type}.{method.lower()}"


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.method not in _MUTATING_METHODS:
            return await call_next(request)

        response = await call_next(request)

        # Fire-and-forget audit write; never block or fail the response.
        try:
            resource_type, resource_id = _extract_resource(request.url.path)

            action = _derive_action(
                request.method,
                str(request.url.path),
                resource_type,
                resource_id,
            )

            # Extract username from auth context middleware identity
            username = None
            user_id = None
            identity = getattr(request.state, "user_identity", None)
            if identity and identity.username:
                username = identity.username

            async with get_db_context() as db:
                entry = AuditLog(
                    timestamp=datetime.utcnow(),
                    user_id=user_id,
                    username=username,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    ip_address=request.client.host if request.client else None,
                    method=request.method,
                    path=str(request.url.path),
                    status_code=str(response.status_code),
                )
                db.add(entry)
        except Exception:
            logger.debug("Audit log write failed", exc_info=True)

        return response
