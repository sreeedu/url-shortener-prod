from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
from app.models.password_reset import PasswordResetToken
from app.core.config import settings


async def create_reset_token(
    db: AsyncSession, user_id: uuid.UUID, token_hash: str
) -> PasswordResetToken:
    # Invalidate all previous unused tokens for this user
    await db.execute(
        delete(PasswordResetToken).where(
            PasswordResetToken.user_id == user_id,
            PasswordResetToken.used_at.is_(None),
        )
    )
    token = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES),
    )
    db.add(token)
    await db.flush()
    return token


async def get_valid_reset_token(
    db: AsyncSession, token_hash: str
) -> Optional[PasswordResetToken]:
    """
    FIX: Added selectinload(PasswordResetToken.user) so that accessing
    reset_token.user in the router doesn't trigger a lazy load, which
    raises MissingGreenlet in async SQLAlchemy.
    The user object is now eagerly loaded in the same query.
    """
    result = await db.execute(
        select(PasswordResetToken)
        .options(selectinload(PasswordResetToken.user))
        .where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(timezone.utc),
        )
    )
    return result.scalar_one_or_none()


async def mark_token_used(db: AsyncSession, token: PasswordResetToken) -> None:
    token.used_at = datetime.now(timezone.utc)
    db.add(token)
    await db.flush()
