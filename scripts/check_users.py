import asyncio
import logging
from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.core.security import hash_password
from sqlalchemy import select

logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        for u in users:
            # Check for the obvious fake testing ones
            if u.email in ["test_ai@example.com", "tempsdf@gmail.com"]:
                u.password_hash = hash_password("Password123")
                db.add(u)
        await db.commit()
        print("Reset passwords to Password123 successfully.")

if __name__ == "__main__":
    asyncio.run(main())
