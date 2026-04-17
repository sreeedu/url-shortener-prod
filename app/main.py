from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
import logging
import time
import uuid

from app.core.config import settings
from app.core.database import init_db, get_db, AsyncSessionLocal
from app.core.redis import get_redis_or_none, close_redis
from app.core.exceptions import AppException
from app.core.limiter import limiter

# Import all models so Alembic and init_db see the full schema
from app.models import User, Project, Link, LinkClick, AuditLog, PasswordResetToken  # noqa: F401

from app.routers import auth, redirect, ai
from app.routers import projects, links, platform

logging.basicConfig(
    level=logging.INFO if settings.APP_ENV == "production" else logging.DEBUG,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} [{settings.APP_ENV}]")

    await init_db()
    logger.info("Database tables verified")

    redis = await get_redis_or_none()
    if redis:
        logger.info("Redis connected")
    else:
        logger.warning(
            "Redis unavailable at startup — redirects will fall back to Postgres."
        )

    yield

    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

app.state.limiter = limiter


# ── Middleware ─────────────────────────────────────────────────────────────────

class LimitRequestSizeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.MAX_REQUEST_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": "Request body too large. Maximum size is 1MB."},
            )
        return await call_next(request)


app.add_middleware(LimitRequestSizeMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

if settings.is_production:
    from urllib.parse import urlparse
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[urlparse(settings.BASE_URL).netloc],
    )


@app.middleware("http")
async def add_request_id_and_log(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} "
        f"→ {response.status_code} ({ms:.1f}ms)"
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ── Exception handlers ─────────────────────────────────────────────────────────

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again."},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        f"[{request_id}] Unhandled exception on {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred"},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router)
app.include_router(links.router)
app.include_router(platform.router)
app.include_router(ai.router, prefix="/api")
app.include_router(redirect.router)   # catch-all must be last


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "ok", "env": settings.APP_ENV, "version": "2.0.0"}


@app.get("/health/ready", tags=["System"])
async def readiness_check():
    # Check DB connectivity
    db_status = "down"
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "up"
    except Exception:
        pass

    redis = await get_redis_or_none()
    overall = "ready" if db_status == "up" else "degraded"

    return {
        "status": overall,
        "database": db_status,
        "redis": "up" if redis else "degraded",
    }
