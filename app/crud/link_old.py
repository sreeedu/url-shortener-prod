import uuid
import logging
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.models.link import Link, LinkClick
from app.schemas.link import CreateLinkRequest, UpdateLinkRequest, EXPIRY_DAYS
from app.core.security import generate_short_code
from app.core.useragent import parse_user_agent, parse_referer
from app.core.reserved_codes import is_reserved

logger = logging.getLogger(__name__)


# ── Short code generation ─────────────────────────────────────────────────────

async def short_code_exists(db: AsyncSession, code: str) -> bool:
    result = await db.execute(select(Link.id).where(Link.short_code == code))
    return result.scalar_one_or_none() is not None


async def generate_unique_short_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = generate_short_code()
        if not is_reserved(code) and not await short_code_exists(db, code):
            return code
    raise RuntimeError("Failed to generate unique short code after 10 attempts")


# ── Link counts ───────────────────────────────────────────────────────────────

async def get_link_count_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Total links across all projects — enforces per-user cap."""
    result = await db.execute(
        select(func.count(Link.id)).where(Link.created_by == user_id)
    )
    return result.scalar_one()


async def get_link_count_for_project(db: AsyncSession, project_id: uuid.UUID) -> int:
    """Links in one project — enforces per-project cap."""
    result = await db.execute(
        select(func.count(Link.id)).where(Link.project_id == project_id)
    )
    return result.scalar_one()


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def get_link_by_short_code(
    db: AsyncSession, short_code: str
) -> Optional[Link]:
    result = await db.execute(
        select(Link).where(Link.short_code == short_code)
    )
    return result.scalar_one_or_none()


async def get_link_by_id(
    db: AsyncSession, link_id: uuid.UUID
) -> Optional[Link]:
    result = await db.execute(select(Link).where(Link.id == link_id))
    return result.scalar_one_or_none()


async def create_link(
    db: AsyncSession,
    project_id: uuid.UUID,
    created_by: uuid.UUID,
    data: CreateLinkRequest,
) -> Link:
    short_code = data.custom_code or await generate_unique_short_code(db)
    expiry_days = EXPIRY_DAYS.get(data.expiry)
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=expiry_days)
        if expiry_days is not None else None
    )
    link = Link(
        project_id=project_id,
        created_by=created_by,
        original_url=str(data.original_url),
        short_code=short_code,
        title=data.title,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(link)
    # Do not catch IntegrityError here — let it propagate to get_db() which
    # owns all rollbacks. Catching and rolling back inside a CRUD function
    # wipes all prior flushes in the same session (e.g. project creation
    # during signup). Concurrent short-code collisions are astronomically
    # rare (62^6 space) and the router pre-checks custom codes before reaching here.
    await db.flush()
    return link


async def get_links_for_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """Return links with click counts — batch query, no N+1."""
    offset = (page - 1) * per_page

    count_result = await db.execute(
        select(func.count(Link.id)).where(Link.project_id == project_id)
    )
    total = count_result.scalar_one()

    links_result = await db.execute(
        select(Link)
        .where(Link.project_id == project_id)
        .order_by(Link.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    links = list(links_result.scalars().all())
    if not links:
        return [], total

    link_ids = [lnk.id for lnk in links]
    counts_result = await db.execute(
        select(LinkClick.link_id, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id.in_(link_ids))
        .group_by(LinkClick.link_id)
    )
    click_counts = {row.link_id: row.cnt for row in counts_result.all()}

    return [
        {"link": lnk, "click_count": click_counts.get(lnk.id, 0)}
        for lnk in links
    ], total


async def update_link(
    db: AsyncSession, link: Link, data: UpdateLinkRequest
) -> Link:
    if data.title is not None:
        link.title = data.title
    if data.is_active is not None:
        link.is_active = data.is_active
    link.updated_at = datetime.now(timezone.utc)
    db.add(link)
    await db.flush()
    return link


async def delete_link(db: AsyncSession, link: Link) -> None:
    await db.delete(link)
    await db.flush()


async def get_click_count(db: AsyncSession, link_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count(LinkClick.id)).where(LinkClick.link_id == link_id)
    )
    return result.scalar_one()


# ── Click recording ───────────────────────────────────────────────────────────

async def record_click_fire_and_forget(
    link_id: uuid.UUID,
    ip_address: Optional[str],
    user_agent: Optional[str],
    referer: Optional[str] = None,
) -> None:
    """
    Fire-and-forget click recording for the redirect hot path.
    Opens its own session — redirect returns before DB write completes.
    UA parsed before write so analytics queries are simple GROUP BY.
    """
    from app.core.database import AsyncSessionLocal

    device_type, browser, os_name = parse_user_agent(user_agent)
    clean_referer = parse_referer(referer)

    try:
        async with AsyncSessionLocal() as session:
            click = LinkClick(
                link_id=link_id,
                ip_address=ip_address,
                user_agent=user_agent[:500] if user_agent else None,
                device_type=device_type,
                browser=browser,
                os=os_name,
                referer=clean_referer,
            )
            session.add(click)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to record click for link_id={link_id}: {e}")


# ── Link analytics ─────────────────────────────────────────────────────────────

async def get_link_analytics(db: AsyncSession, link_id: uuid.UUID) -> dict:
    """
    8 analytics queries run sequentially on the shared session.

    NOTE: asyncio.gather() was removed. AsyncSession wraps a single DB
    connection — firing concurrent coroutines against it causes interleaved
    cursor reads and silent data corruption. Sequential awaits are safe and
    still fast because each query is a single round-trip aggregate.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # 1. Time-range counts + unique visitors
    counts_r = await db.execute(select(
        func.count(LinkClick.id).label("total_clicks"),
        func.count(case((LinkClick.clicked_at >= today_start, LinkClick.id))).label("clicks_today"),
        func.count(case((LinkClick.clicked_at >= week_start, LinkClick.id))).label("clicks_this_week"),
        func.count(case((LinkClick.clicked_at >= month_start, LinkClick.id))).label("clicks_this_month"),
        func.count(func.distinct(LinkClick.ip_address)).label("unique_visitors"),
    ).where(LinkClick.link_id == link_id))

    # 2. Device breakdown
    device_r = await db.execute(
        select(LinkClick.device_type, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id == link_id)
        .where(LinkClick.device_type.isnot(None))
        .group_by(LinkClick.device_type)
        .order_by(func.count(LinkClick.id).desc())
    )

    # 3. Browser breakdown — top 10, no bots
    browser_r = await db.execute(
        select(LinkClick.browser, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id == link_id)
        .where(LinkClick.browser.isnot(None))
        .where(LinkClick.browser.notin_(["bot", "unknown"]))
        .group_by(LinkClick.browser)
        .order_by(func.count(LinkClick.id).desc())
        .limit(10)
    )

    # 4. OS breakdown — top 10, no bots
    os_r = await db.execute(
        select(LinkClick.os, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id == link_id)
        .where(LinkClick.os.isnot(None))
        .where(LinkClick.os.notin_(["bot", "unknown"]))
        .group_by(LinkClick.os)
        .order_by(func.count(LinkClick.id).desc())
        .limit(10)
    )

    # 5. Referers — top 10
    referer_r = await db.execute(
        select(LinkClick.referer, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id == link_id)
        .where(LinkClick.referer.isnot(None))
        .group_by(LinkClick.referer)
        .order_by(func.count(LinkClick.id).desc())
        .limit(10)
    )

    # 6. Timeline — last 30 days daily
    timeline_r = await db.execute(
        select(
            func.date(LinkClick.clicked_at).label("day"),
            func.count(LinkClick.id).label("cnt"),
        )
        .where(LinkClick.link_id == link_id)
        .where(LinkClick.clicked_at >= month_start)
        .group_by(func.date(LinkClick.clicked_at))
        .order_by(func.date(LinkClick.clicked_at))
    )

    # 7. Peak hour
    peak_r = await db.execute(
        select(
            func.extract("hour", LinkClick.clicked_at).label("hour"),
            func.count(LinkClick.id).label("cnt"),
        )
        .where(LinkClick.link_id == link_id)
        .group_by(func.extract("hour", LinkClick.clicked_at))
        .order_by(func.count(LinkClick.id).desc())
        .limit(1)
    )

    # 8. Bot vs human
    bot_r = await db.execute(
        select(
            func.count(case((LinkClick.device_type == "bot", LinkClick.id))).label("bot_clicks"),
            func.count(case((LinkClick.device_type != "bot", LinkClick.id))).label("human_clicks"),
        ).where(LinkClick.link_id == link_id)
    )

    counts = counts_r.one()
    peak_row = peak_r.first()
    bot_row = bot_r.one()

    return {
        "total_clicks": counts.total_clicks,
        "unique_visitors": counts.unique_visitors,
        "clicks_today": counts.clicks_today,
        "clicks_this_week": counts.clicks_this_week,
        "clicks_this_month": counts.clicks_this_month,
        "devices": {r.device_type: r.cnt for r in device_r.all()},
        "browsers": {r.browser: r.cnt for r in browser_r.all()},
        "os_breakdown": {r.os: r.cnt for r in os_r.all()},
        "referers": {r.referer: r.cnt for r in referer_r.all()},
        "clicks_over_time": [
            {"date": str(r.day), "clicks": r.cnt} for r in timeline_r.all()
        ],
        "peak_hour": int(peak_row.hour) if peak_row else None,
        "bot_clicks": bot_row.bot_clicks,
        "human_clicks": bot_row.human_clicks,
    }

# import uuid
# import logging
# import asyncio
# from typing import Optional
# from datetime import datetime, timedelta, timezone

# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, func, case
# from sqlalchemy.exc import IntegrityError

# from app.models.link import Link, LinkClick
# from app.schemas.link import CreateLinkRequest, UpdateLinkRequest, EXPIRY_DAYS
# from app.core.security import generate_short_code
# from app.core.useragent import parse_user_agent, parse_referer

# logger = logging.getLogger(__name__)


# # ── Short code generation ─────────────────────────────────────────────────────

# async def short_code_exists(db: AsyncSession, code: str) -> bool:
#     result = await db.execute(select(Link.id).where(Link.short_code == code))
#     return result.scalar_one_or_none() is not None


# async def generate_unique_short_code(db: AsyncSession) -> str:
#     for _ in range(10):
#         code = generate_short_code()
#         if not await short_code_exists(db, code):
#             return code
#     raise RuntimeError("Failed to generate unique short code after 10 attempts")


# # ── Link counts ───────────────────────────────────────────────────────────────

# async def get_link_count_for_user(db: AsyncSession, user_id: uuid.UUID) -> int:
#     """Total links across all projects — enforces per-user cap."""
#     result = await db.execute(
#         select(func.count(Link.id)).where(Link.created_by == user_id)
#     )
#     return result.scalar_one()


# async def get_link_count_for_project(db: AsyncSession, project_id: uuid.UUID) -> int:
#     """Links in one project — enforces per-project cap."""
#     result = await db.execute(
#         select(func.count(Link.id)).where(Link.project_id == project_id)
#     )
#     return result.scalar_one()


# # ── CRUD ──────────────────────────────────────────────────────────────────────

# async def get_link_by_short_code(
#     db: AsyncSession, short_code: str
# ) -> Optional[Link]:
#     result = await db.execute(
#         select(Link).where(Link.short_code == short_code)
#     )
#     return result.scalar_one_or_none()


# async def get_link_by_id(
#     db: AsyncSession, link_id: uuid.UUID
# ) -> Optional[Link]:
#     result = await db.execute(select(Link).where(Link.id == link_id))
#     return result.scalar_one_or_none()


# async def create_link(
#     db: AsyncSession,
#     project_id: uuid.UUID,
#     created_by: uuid.UUID,
#     data: CreateLinkRequest,
# ) -> Link:
#     short_code = data.custom_code or await generate_unique_short_code(db)
#     expiry_days = EXPIRY_DAYS.get(data.expiry)
#     expires_at = (
#         datetime.now(timezone.utc) + timedelta(days=expiry_days)
#         if expiry_days is not None else None
#     )
#     link = Link(
#         project_id=project_id,
#         created_by=created_by,
#         original_url=str(data.original_url),
#         short_code=short_code,
#         title=data.title,
#         expires_at=expires_at,
#         is_active=True,
#     )
#     db.add(link)
#     try:
#         await db.flush()
#     except IntegrityError:
#         # Concurrent insert with same short code — should be extremely rare
#         await db.rollback()
#         raise
#     return link


# async def get_links_for_project(
#     db: AsyncSession,
#     project_id: uuid.UUID,
#     page: int = 1,
#     per_page: int = 20,
# ) -> tuple[list[dict], int]:
#     """Return links with click counts — batch query, no N+1."""
#     offset = (page - 1) * per_page

#     count_result = await db.execute(
#         select(func.count(Link.id)).where(Link.project_id == project_id)
#     )
#     total = count_result.scalar_one()

#     links_result = await db.execute(
#         select(Link)
#         .where(Link.project_id == project_id)
#         .order_by(Link.created_at.desc())
#         .offset(offset)
#         .limit(per_page)
#     )
#     links = list(links_result.scalars().all())
#     if not links:
#         return [], total

#     link_ids = [lnk.id for lnk in links]
#     counts_result = await db.execute(
#         select(LinkClick.link_id, func.count(LinkClick.id).label("cnt"))
#         .where(LinkClick.link_id.in_(link_ids))
#         .group_by(LinkClick.link_id)
#     )
#     click_counts = {row.link_id: row.cnt for row in counts_result.all()}

#     return [
#         {"link": lnk, "click_count": click_counts.get(lnk.id, 0)}
#         for lnk in links
#     ], total


# async def update_link(
#     db: AsyncSession, link: Link, data: UpdateLinkRequest
# ) -> Link:
#     if data.title is not None:
#         link.title = data.title
#     if data.is_active is not None:
#         link.is_active = data.is_active
#     link.updated_at = datetime.now(timezone.utc)
#     db.add(link)
#     await db.flush()
#     return link


# async def delete_link(db: AsyncSession, link: Link) -> None:
#     await db.delete(link)
#     await db.flush()


# async def get_click_count(db: AsyncSession, link_id: uuid.UUID) -> int:
#     result = await db.execute(
#         select(func.count(LinkClick.id)).where(LinkClick.link_id == link_id)
#     )
#     return result.scalar_one()


# # ── Click recording ───────────────────────────────────────────────────────────

# async def record_click_fire_and_forget(
#     link_id: uuid.UUID,
#     ip_address: Optional[str],
#     user_agent: Optional[str],
#     referer: Optional[str] = None,
# ) -> None:
#     """
#     Fire-and-forget click recording for the redirect hot path.
#     Opens its own session — redirect returns before DB write completes.
#     UA parsed before write so analytics queries are simple GROUP BY.
#     """
#     from app.core.database import AsyncSessionLocal

#     device_type, browser, os_name = parse_user_agent(user_agent)
#     clean_referer = parse_referer(referer)

#     try:
#         async with AsyncSessionLocal() as session:
#             click = LinkClick(
#                 link_id=link_id,
#                 ip_address=ip_address,
#                 user_agent=user_agent[:500] if user_agent else None,
#                 device_type=device_type,
#                 browser=browser,
#                 os=os_name,
#                 referer=clean_referer,
#             )
#             session.add(click)
#             await session.commit()
#     except Exception as e:
#         logger.warning(f"Failed to record click for link_id={link_id}: {e}")


# # ── Link analytics ─────────────────────────────────────────────────────────────

# async def get_link_analytics(db: AsyncSession, link_id: uuid.UUID) -> dict:
#     """
#     All 8 analytics queries run concurrently via asyncio.gather.
#     Total latency = slowest query, not sum of all 8.
#     """
#     now = datetime.now(timezone.utc)
#     today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
#     week_start = now - timedelta(days=7)
#     month_start = now - timedelta(days=30)

#     async def run(q):
#         return await db.execute(q)

#     (
#         counts_r, device_r, browser_r, os_r,
#         referer_r, timeline_r, peak_r, bot_r,
#     ) = await asyncio.gather(
#         # 1. Time-range counts + unique visitors
#         run(select(
#             func.count(LinkClick.id).label("total_clicks"),
#             func.count(case((LinkClick.clicked_at >= today_start, LinkClick.id))).label("clicks_today"),
#             func.count(case((LinkClick.clicked_at >= week_start, LinkClick.id))).label("clicks_this_week"),
#             func.count(case((LinkClick.clicked_at >= month_start, LinkClick.id))).label("clicks_this_month"),
#             func.count(func.distinct(LinkClick.ip_address)).label("unique_visitors"),
#         ).where(LinkClick.link_id == link_id)),

#         # 2. Device breakdown
#         run(select(LinkClick.device_type, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id == link_id)
#             .where(LinkClick.device_type.isnot(None))
#             .group_by(LinkClick.device_type)
#             .order_by(func.count(LinkClick.id).desc())),

#         # 3. Browser breakdown — top 10, no bots
#         run(select(LinkClick.browser, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id == link_id)
#             .where(LinkClick.browser.isnot(None))
#             .where(LinkClick.browser.notin_(["bot", "unknown"]))
#             .group_by(LinkClick.browser)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(10)),

#         # 4. OS breakdown — top 10, no bots
#         run(select(LinkClick.os, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id == link_id)
#             .where(LinkClick.os.isnot(None))
#             .where(LinkClick.os.notin_(["bot", "unknown"]))
#             .group_by(LinkClick.os)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(10)),

#         # 5. Referers — top 10
#         run(select(LinkClick.referer, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id == link_id)
#             .where(LinkClick.referer.isnot(None))
#             .group_by(LinkClick.referer)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(10)),

#         # 6. Timeline — last 30 days daily
#         run(select(
#             func.date(LinkClick.clicked_at).label("day"),
#             func.count(LinkClick.id).label("cnt"),
#         )
#             .where(LinkClick.link_id == link_id)
#             .where(LinkClick.clicked_at >= month_start)
#             .group_by(func.date(LinkClick.clicked_at))
#             .order_by(func.date(LinkClick.clicked_at))),

#         # 7. Peak hour
#         run(select(
#             func.extract("hour", LinkClick.clicked_at).label("hour"),
#             func.count(LinkClick.id).label("cnt"),
#         )
#             .where(LinkClick.link_id == link_id)
#             .group_by(func.extract("hour", LinkClick.clicked_at))
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(1)),

#         # 8. Bot vs human
#         run(select(
#             func.count(case((LinkClick.device_type == "bot", LinkClick.id))).label("bot_clicks"),
#             func.count(case((LinkClick.device_type != "bot", LinkClick.id))).label("human_clicks"),
#         ).where(LinkClick.link_id == link_id)),
#     )

#     counts = counts_r.one()
#     peak_row = peak_r.first()
#     bot_row = bot_r.one()

#     return {
#         "total_clicks": counts.total_clicks,
#         "unique_visitors": counts.unique_visitors,
#         "clicks_today": counts.clicks_today,
#         "clicks_this_week": counts.clicks_this_week,
#         "clicks_this_month": counts.clicks_this_month,
#         "devices": {r.device_type: r.cnt for r in device_r.all()},
#         "browsers": {r.browser: r.cnt for r in browser_r.all()},
#         "os_breakdown": {r.os: r.cnt for r in os_r.all()},
#         "referers": {r.referer: r.cnt for r in referer_r.all()},
#         "clicks_over_time": [
#             {"date": str(r.day), "clicks": r.cnt} for r in timeline_r.all()
#         ],
#         "peak_hour": int(peak_row.hour) if peak_row else None,
#         "bot_clicks": bot_row.bot_clicks,
#         "human_clicks": bot_row.human_clicks,
#     }
