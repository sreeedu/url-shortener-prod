from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.core.config import settings


# ── Sanitise DATABASE_URL for asyncpg compatibility ──────────────────────────
# 1. Supabase/Render provide postgresql:// — asyncpg needs postgresql+asyncpg://
# 2. Supabase pooler URLs add ?pgbouncer=true which asyncpg rejects
# NOTE: We avoid urllib.parse.urlparse because Python 3.14 added strict
#       bracketed-netloc validation that crashes on Supabase passwords
#       containing special characters.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://"):
    _db_url = _db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Strip query params that asyncpg doesn't understand (pgbouncer, etc.)
_bad_params = ("pgbouncer", "prepared_statements")
if "?" in _db_url:
    _base, _qs = _db_url.split("?", 1)
    _kept = [p for p in _qs.split("&") if p.split("=")[0] not in _bad_params]
    _db_url = f"{_base}?{'&'.join(_kept)}" if _kept else _base

# When using Supabase's PgBouncer (transaction mode), prepared statements
# must be disabled on the asyncpg side as well.
_connect_args = {"command_timeout": settings.DB_QUERY_TIMEOUT}
if "pgbouncer" in settings.DATABASE_URL:
    _connect_args["prepared_statement_cache_size"] = 0

engine = create_async_engine(
    _db_url,
    echo=settings.APP_ENV == "development",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def init_db():
    """
    Creates all tables from SQLAlchemy models on startup.
    Safe to call multiple times — CREATE TABLE IF NOT EXISTS.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db():
    """Dependency: yields a session, commits on success, rolls back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
