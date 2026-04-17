"""
Bootstrap script: grant platform admin to a user by email.

Usage:
    python -m scripts.make_admin admin@yourdomain.com

Run from the project root (where alembic.ini lives).
This is the ONLY safe way to set is_platform_admin — it is never
settable via the API.
"""

import asyncio
import sys
from pathlib import Path

# Ensure app is importable from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.models.user import User


async def make_admin(email: str) -> None:
    email = email.lower().strip()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        if not user:
            print(f"ERROR: No user found with email '{email}'")
            sys.exit(1)

        if user.is_platform_admin:
            print(f"INFO: {email} is already a platform admin. No change made.")
            return

        user.is_platform_admin = True
        db.add(user)
        await db.commit()
        print(f"SUCCESS: {email} is now a platform admin.")
        print(f"User ID: {user.id}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.make_admin <email>")
        sys.exit(1)
    asyncio.run(make_admin(sys.argv[1]))
