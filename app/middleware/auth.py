from fastapi import Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.database import get_db
from app.core.security import decode_token
from app.core.exceptions import InvalidTokenError, UserNotFoundError, PlatformAdminRequiredError
from app.crud.user import get_user_by_id
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise InvalidTokenError()

    # Reject suspiciously long tokens before any crypto — DoS prevention
    if len(credentials.credentials) > 2048:
        raise InvalidTokenError()

    user_id_str = decode_token(credentials.credentials, token_type="access")
    if not user_id_str:
        raise InvalidTokenError()

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise InvalidTokenError()

    user = await get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError()

    if not user.is_active:
        raise InvalidTokenError()

    return user


async def get_platform_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency for platform admin endpoints.
    Requires is_platform_admin=True — only set via make_admin.py script.
    """
    if not current_user.is_platform_admin:
        raise PlatformAdminRequiredError()
    return current_user
