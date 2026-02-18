"""API dependencies for dependency injection."""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import Depends, Header, HTTPException, WebSocket, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, ExpiredSignatureError, jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings, Settings
from app.database import get_db_context, get_read_db
from app.models.api_key import ApiKey
from app.models.user import User, UserRole, role_at_least

settings = get_settings()
logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.api_v1_prefix}/auth/token", auto_error=False
)


def get_settings_dep() -> Settings:
    """Dependency for getting settings."""
    return get_settings()


async def _authenticate_api_key(
    db: AsyncSession, api_key: str
) -> Optional[User]:
    """Validate an X-API-Key header and return a synthetic service user."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_active.is_(True),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    # Check expiry
    if row.expires_at and row.expires_at < datetime.utcnow():
        return None

    await _touch_api_key_last_used(row.id)

    # Return a synthetic user object for downstream compatibility
    user = User(
        username=f"svc:{row.service_name}",
        email=f"{row.service_name}@internal",
        hashed_password="",
        is_active=True,
        is_superuser=False,
        role=UserRole.OPERATOR,
    )
    user.id = row.id  # Reuse key ID as user ID for audit trail
    return user


async def _touch_api_key_last_used(api_key_id) -> None:
    """Best-effort last-used timestamp update (separate write session)."""
    try:
        async with get_db_context() as db:
            await db.execute(
                update(ApiKey)
                .where(ApiKey.id == api_key_id)
                .values(last_used_at=datetime.utcnow())
            )
    except Exception:
        logger.debug("Failed to update API key last_used_at", exc_info=True)


async def get_current_user(
    token: Annotated[Optional[str], Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_read_db)],
    x_api_key: Optional[str] = Header(None),
) -> User:
    """Authenticate via JWT bearer token or X-API-Key header."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Try API key first (service-to-service)
    if x_api_key:
        user = await _authenticate_api_key(db, x_api_key)
        if user:
            return user
        raise credentials_exception

    # Fall back to JWT
    if not token:
        raise credentials_exception

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={
                "WWW-Authenticate": 'Bearer error="invalid_token"',
                "X-Token-Expired": "true",
            },
        )
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current active user."""
    return current_user


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get current superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def ws_authenticate(
    websocket: WebSocket,
    db: AsyncSession,
) -> User:
    """
    Authenticate a WebSocket connection using a JWT token from query params.

    Extracts ?token=<jwt> from the WebSocket URL, validates it, and returns the user.
    Closes the WebSocket with code 4401 if authentication fails.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401)
        raise HTTPException(status_code=401, detail="Missing token")

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        ws_username: str | None = payload.get("sub")
        if ws_username is None:
            await websocket.close(code=4401)
            raise HTTPException(status_code=401, detail="Invalid token")
    except ExpiredSignatureError:
        await websocket.close(code=4401, reason="Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError:
        await websocket.close(code=4401)
        raise HTTPException(status_code=401, detail="Invalid token")

    result = await db.execute(select(User).where(User.username == ws_username))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        await websocket.close(code=4401)
        raise HTTPException(status_code=401, detail="Invalid user")

    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def require_role(minimum: UserRole):
    """Dependency factory that enforces a minimum role level.

    Usage::

        @router.post("/admin-only")
        async def admin_only(user: CurrentUser = Depends(require_role(UserRole.ADMIN))):
            ...
    """
    async def _check(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not role_at_least(current_user.role, minimum):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{minimum.value}' or higher required",
            )
        return current_user

    return _check


# Type aliases for cleaner function signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
ActiveUser = Annotated[User, Depends(get_current_active_user)]
SuperUser = Annotated[User, Depends(get_current_superuser)]
OperatorUser = Annotated[User, Depends(require_role(UserRole.OPERATOR))]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
DBSession = Annotated[AsyncSession, Depends(get_read_db)]
