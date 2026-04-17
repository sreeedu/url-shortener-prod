from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone
import uuid

from app.models.user import User
from app.core.security import hash_password


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(
        select(User).where(User.email == email.lower().strip())
    )
    return result.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def create_user(db: AsyncSession, email: str, password: str) -> User:
    user = User(
        email=email.lower().strip(),
        password_hash=hash_password(password),
        is_active=True,
        is_verified=False,
        is_platform_admin=False,
    )
    db.add(user)
    await db.flush()
    return user


async def update_password(db: AsyncSession, user: User, new_password: str) -> User:
    user.password_hash = hash_password(new_password)
    db.add(user)
    await db.flush()
    return user


async def update_last_login(db: AsyncSession, user: User) -> None:
    """Called on every successful login — used in platform admin panel."""
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    await db.flush()
