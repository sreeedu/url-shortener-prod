from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
import asyncio
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.redis import get_redis_or_none, url_cache_key, url_id_cache_key
from app.core.exceptions import LinkNotFoundError, LinkExpiredError, LinkInactiveError
from app.core.limiter import limiter
from app.core.config import settings
from app.crud.link import get_link_by_short_code, record_click_fire_and_forget

router = APIRouter(tags=["Redirect"])

# Strong references to in-flight click-recording tasks.
# Prevents the GC from cancelling tasks before they complete under high load.
_click_tasks: set[asyncio.Task] = set()


def _fire_click_task(link_id: uuid.UUID, ip, ua, referer) -> None:
    """Create a tracked fire-and-forget task for click recording."""
    task = asyncio.create_task(
        record_click_fire_and_forget(link_id, ip, ua, referer)
    )
    _click_tasks.add(task)
    task.add_done_callback(_click_tasks.discard)


@router.get("/{short_code}", include_in_schema=False)
@limiter.limit(settings.RATE_LIMIT_REDIRECT)
async def redirect_to_url(
    short_code: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    referer = request.headers.get("referer") or request.headers.get("referrer")

    # ── Redis fast path ───────────────────────────────────────────────────
    redis = await get_redis_or_none()
    if redis:
        try:
            cached_url = await redis.get(url_cache_key(short_code))
            if cached_url:
                link_id_str = await redis.get(url_id_cache_key(short_code))
                if link_id_str:
                    _fire_click_task(uuid.UUID(link_id_str), ip, ua, referer)
                return RedirectResponse(url=cached_url, status_code=302)
        except Exception:
            pass

    # ── Postgres fallback ─────────────────────────────────────────────────
    link = await get_link_by_short_code(db, short_code)

    if not link:
        raise LinkNotFoundError()
    if not link.is_active:
        raise LinkInactiveError()
    if link.expires_at and link.expires_at < datetime.now(timezone.utc):
        raise LinkExpiredError()

    _fire_click_task(link.id, ip, ua, referer)

    if redis:
        try:
            cache_key = url_cache_key(short_code)
            id_key = url_id_cache_key(short_code)
            if link.expires_at:
                ttl = int((link.expires_at - datetime.now(timezone.utc)).total_seconds())
                if ttl > 0:
                    await redis.setex(cache_key, ttl, link.original_url)
                    await redis.setex(id_key, ttl, str(link.id))
            else:
                await redis.setex(cache_key, 86400, link.original_url)
                await redis.setex(id_key, 86400, str(link.id))
        except Exception:
            pass

    return RedirectResponse(url=link.original_url, status_code=302)
