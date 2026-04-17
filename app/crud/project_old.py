import uuid
import logging
import re
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case

from app.models.project import Project
from app.models.link import Link, LinkClick
from app.schemas.project import CreateProjectRequest, UpdateProjectRequest
from app.core.exceptions import ProjectSlugTakenError

logger = logging.getLogger(__name__)


# ── Slug generation ───────────────────────────────────────────────────────────

def _slugify(name: str) -> str:
    """Convert project name to URL-safe slug: 'Summer Campaign' → 'summer-campaign'."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)       # remove non-word chars
    slug = re.sub(r"[\s_]+", "-", slug)         # spaces/underscores → hyphens
    slug = re.sub(r"-+", "-", slug)             # collapse multiple hyphens
    slug = slug.strip("-")                       # trim leading/trailing hyphens
    return slug[:100] or "project"              # cap at 100, never empty


async def _unique_slug(
    db: AsyncSession,
    base_slug: str,
    owner_user_id: Optional[uuid.UUID],
    owner_org_id: Optional[uuid.UUID],
    exclude_project_id: Optional[uuid.UUID] = None,
) -> str:
    """
    Return a slug guaranteed unique for this owner.
    Appends -2, -3 ... -10 on collision.
    Uses a single IN query instead of up to 9 sequential SELECTs.
    Raises ProjectSlugTakenError if all suffixes are taken (extremely unlikely).
    """
    candidates = [base_slug] + [f"{base_slug}-{i}" for i in range(2, 11)]

    q = select(Project.slug).where(Project.slug.in_(candidates))
    if owner_user_id:
        q = q.where(Project.owner_user_id == owner_user_id)
    else:
        q = q.where(Project.owner_org_id == owner_org_id)
    if exclude_project_id:
        q = q.where(Project.id != exclude_project_id)

    result = await db.execute(q)
    taken = {row.slug for row in result.all()}

    for candidate in candidates:
        if candidate not in taken:
            return candidate

    raise ProjectSlugTakenError()


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def get_project_by_id(
    db: AsyncSession, project_id: uuid.UUID
) -> Optional[Project]:
    result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def get_default_project_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> Optional[Project]:
    result = await db.execute(
        select(Project).where(
            Project.owner_user_id == user_id,
            Project.is_default == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


async def get_project_count_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> int:
    result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_user_id == user_id)
    )
    return result.scalar_one()


async def create_project(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    data: CreateProjectRequest,
    is_default: bool = False,
) -> Project:
    """
    Create a project. _unique_slug() does an optimistic availability check
    before the insert. On the extremely rare concurrent collision the
    IntegrityError propagates up to get_db() which rolls back the whole
    transaction — never call rollback() inside a CRUD function because it
    wipes all prior flushes (e.g. create_user) in the same request session.
    """
    base_slug = _slugify(data.name)
    slug = await _unique_slug(db, base_slug, owner_user_id, None)

    project = Project(
        owner_user_id=owner_user_id,
        owner_org_id=None,
        name=data.name,
        slug=slug,
        description=data.description,
        color=data.color,
        is_default=is_default,
        is_active=True,
    )
    db.add(project)
    await db.flush()
    return project


async def create_default_project(
    db: AsyncSession, owner_user_id: uuid.UUID
) -> Project:
    """Create the auto Personal project for a new user."""
    from app.schemas.project import CreateProjectRequest as CPR
    data = CPR(name="Personal", description="Your default personal project")
    return await create_project(db, owner_user_id, data, is_default=True)


async def update_project(
    db: AsyncSession,
    project: Project,
    data: UpdateProjectRequest,
) -> Project:
    if data.name is not None and data.name != project.name:
        base_slug = _slugify(data.name)
        project.slug = await _unique_slug(
            db, base_slug, project.owner_user_id, project.owner_org_id,
            exclude_project_id=project.id,
        )
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    if data.color is not None:
        project.color = data.color
    if data.is_active is not None:
        project.is_active = data.is_active
    project.updated_at = datetime.now(timezone.utc)
    db.add(project)
    await db.flush()
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    await db.delete(project)
    await db.flush()


async def get_link_count_for_project(
    db: AsyncSession, project_id: uuid.UUID
) -> int:
    result = await db.execute(
        select(func.count(Link.id)).where(Link.project_id == project_id)
    )
    return result.scalar_one()


# ── Project list with click aggregates ───────────────────────────────────────

async def get_projects_for_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[dict], int]:
    """
    Return projects with pre-aggregated link_count, total_clicks,
    clicks_this_month. Uses a single batch query per stat — no N+1.
    """
    from datetime import timedelta
    offset = (page - 1) * per_page

    # Total count
    count_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_user_id == user_id)
    )
    total = count_result.scalar_one()

    # Projects page
    proj_result = await db.execute(
        select(Project)
        .where(Project.owner_user_id == user_id)
        .order_by(Project.is_default.desc(), Project.created_at.asc())
        .offset(offset)
        .limit(per_page)
    )
    projects = list(proj_result.scalars().all())
    if not projects:
        return [], total

    project_ids = [p.id for p in projects]
    now = datetime.now(timezone.utc)
    month_start = now - timedelta(days=30)

    # Batch: link count per project
    link_counts_result = await db.execute(
        select(Link.project_id, func.count(Link.id).label("cnt"))
        .where(Link.project_id.in_(project_ids))
        .group_by(Link.project_id)
    )
    link_counts = {row.project_id: row.cnt for row in link_counts_result.all()}

    # Batch: total clicks and monthly clicks per project — one query
    click_stats_result = await db.execute(
        select(
            Link.project_id,
            func.count(LinkClick.id).label("total_clicks"),
            func.count(
                case((LinkClick.clicked_at >= month_start, LinkClick.id))
            ).label("clicks_this_month"),
        )
        .join(LinkClick, LinkClick.link_id == Link.id, isouter=True)
        .where(Link.project_id.in_(project_ids))
        .group_by(Link.project_id)
    )
    click_stats = {
        row.project_id: {
            "total_clicks": row.total_clicks,
            "clicks_this_month": row.clicks_this_month,
        }
        for row in click_stats_result.all()
    }

    enriched = []
    for p in projects:
        stats = click_stats.get(p.id, {"total_clicks": 0, "clicks_this_month": 0})
        enriched.append({
            "project": p,
            "link_count": link_counts.get(p.id, 0),
            "total_clicks": stats["total_clicks"],
            "clicks_this_month": stats["clicks_this_month"],
        })

    return enriched, total


# ── Project analytics ─────────────────────────────────────────────────────────

async def get_project_analytics(
    db: AsyncSession, project_id: uuid.UUID
) -> dict:
    """
    10 analytics queries run sequentially on the shared session.

    NOTE: asyncio.gather() was removed. AsyncSession wraps a single DB
    connection — firing concurrent coroutines against it causes interleaved
    cursor reads and silent data corruption. Sequential awaits are safe and
    still fast because each query is a single round-trip aggregate.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # Subquery: link IDs in this project
    link_ids_subq = select(Link.id).where(Link.project_id == project_id).scalar_subquery()

    # 1. Link counts
    link_counts_r = await db.execute(select(
        func.count(Link.id).label("total"),
        func.count(case((Link.is_active == True, Link.id))).label("active"),  # noqa: E712
    ).where(Link.project_id == project_id))

    # 2. Click time-range counts
    counts_r = await db.execute(select(
        func.count(LinkClick.id).label("total_clicks"),
        func.count(case((LinkClick.clicked_at >= today_start, LinkClick.id))).label("clicks_today"),
        func.count(case((LinkClick.clicked_at >= week_start, LinkClick.id))).label("clicks_this_week"),
        func.count(case((LinkClick.clicked_at >= month_start, LinkClick.id))).label("clicks_this_month"),
        func.count(func.distinct(LinkClick.ip_address)).label("unique_visitors"),
    ).where(LinkClick.link_id.in_(link_ids_subq)))

    # 3. Device breakdown
    device_r = await db.execute(
        select(LinkClick.device_type, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id.in_(link_ids_subq))
        .where(LinkClick.device_type.isnot(None))
        .group_by(LinkClick.device_type)
        .order_by(func.count(LinkClick.id).desc())
    )

    # 4. Browser breakdown (top 10, no bots)
    browser_r = await db.execute(
        select(LinkClick.browser, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id.in_(link_ids_subq))
        .where(LinkClick.browser.isnot(None))
        .where(LinkClick.browser.notin_(["bot", "unknown"]))
        .group_by(LinkClick.browser)
        .order_by(func.count(LinkClick.id).desc())
        .limit(10)
    )

    # 5. OS breakdown (top 10, no bots)
    os_r = await db.execute(
        select(LinkClick.os, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id.in_(link_ids_subq))
        .where(LinkClick.os.isnot(None))
        .where(LinkClick.os.notin_(["bot", "unknown"]))
        .group_by(LinkClick.os)
        .order_by(func.count(LinkClick.id).desc())
        .limit(10)
    )

    # 6. Referers (top 10)
    referer_r = await db.execute(
        select(LinkClick.referer, func.count(LinkClick.id).label("cnt"))
        .where(LinkClick.link_id.in_(link_ids_subq))
        .where(LinkClick.referer.isnot(None))
        .group_by(LinkClick.referer)
        .order_by(func.count(LinkClick.id).desc())
        .limit(10)
    )

    # 7. Timeline — last 30 days
    timeline_r = await db.execute(
        select(
            func.date(LinkClick.clicked_at).label("day"),
            func.count(LinkClick.id).label("cnt"),
        )
        .where(LinkClick.link_id.in_(link_ids_subq))
        .where(LinkClick.clicked_at >= month_start)
        .group_by(func.date(LinkClick.clicked_at))
        .order_by(func.date(LinkClick.clicked_at))
    )

    # 8. Peak hour
    peak_r = await db.execute(
        select(
            func.extract("hour", LinkClick.clicked_at).label("hour"),
            func.count(LinkClick.id).label("cnt"),
        )
        .where(LinkClick.link_id.in_(link_ids_subq))
        .group_by(func.extract("hour", LinkClick.clicked_at))
        .order_by(func.count(LinkClick.id).desc())
        .limit(1)
    )

    # 9. Bot vs human split
    bot_r = await db.execute(
        select(
            func.count(case((LinkClick.device_type == "bot", LinkClick.id))).label("bot_clicks"),
            func.count(case((LinkClick.device_type != "bot", LinkClick.id))).label("human_clicks"),
        ).where(LinkClick.link_id.in_(link_ids_subq))
    )

    # 10. Top 5 links in project
    top_links_r = await db.execute(
        select(
            Link.id,
            Link.short_code,
            Link.title,
            func.count(LinkClick.id).label("clicks"),
        )
        .join(LinkClick, LinkClick.link_id == Link.id, isouter=True)
        .where(Link.project_id == project_id)
        .group_by(Link.id, Link.short_code, Link.title)
        .order_by(func.count(LinkClick.id).desc())
        .limit(5)
    )

    link_counts_row = link_counts_r.one()
    counts = counts_r.one()
    peak_row = peak_r.first()
    bot_row = bot_r.one()

    return {
        "total_links": link_counts_row.total,
        "active_links": link_counts_row.active,
        "total_clicks": counts.total_clicks,
        "unique_visitors": counts.unique_visitors,
        "clicks_today": counts.clicks_today,
        "clicks_this_week": counts.clicks_this_week,
        "clicks_this_month": counts.clicks_this_month,
        "top_links": [
            {
                "link_id": str(r.id),
                "short_code": r.short_code,
                "title": r.title,
                "clicks": r.clicks,
            }
            for r in top_links_r.all()
        ],
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
# import re
# from typing import Optional
# from datetime import datetime, timezone

# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, func, case
# from sqlalchemy.exc import IntegrityError

# from app.models.project import Project
# from app.models.link import Link, LinkClick
# from app.schemas.project import CreateProjectRequest, UpdateProjectRequest
# from app.core.exceptions import ProjectSlugTakenError

# logger = logging.getLogger(__name__)


# # ── Slug generation ───────────────────────────────────────────────────────────

# def _slugify(name: str) -> str:
#     """Convert project name to URL-safe slug: 'Summer Campaign' → 'summer-campaign'."""
#     slug = name.lower().strip()
#     slug = re.sub(r"[^\w\s-]", "", slug)       # remove non-word chars
#     slug = re.sub(r"[\s_]+", "-", slug)         # spaces/underscores → hyphens
#     slug = re.sub(r"-+", "-", slug)             # collapse multiple hyphens
#     slug = slug.strip("-")                       # trim leading/trailing hyphens
#     return slug[:100] or "project"              # cap at 100, never empty


# async def _unique_slug(
#     db: AsyncSession,
#     base_slug: str,
#     owner_user_id: Optional[uuid.UUID],
#     owner_org_id: Optional[uuid.UUID],
#     exclude_project_id: Optional[uuid.UUID] = None,
# ) -> str:
#     """
#     Return a slug guaranteed unique for this owner.
#     Appends -2, -3 ... -10 on collision.
#     Raises ProjectSlugTakenError if all suffixes are taken (extremely unlikely).
#     """
#     candidates = [base_slug] + [f"{base_slug}-{i}" for i in range(2, 11)]

#     for candidate in candidates:
#         q = select(Project.id).where(Project.slug == candidate)
#         if owner_user_id:
#             q = q.where(Project.owner_user_id == owner_user_id)
#         else:
#             q = q.where(Project.owner_org_id == owner_org_id)
#         if exclude_project_id:
#             q = q.where(Project.id != exclude_project_id)

#         result = await db.execute(q)
#         if result.scalar_one_or_none() is None:
#             return candidate

#     raise ProjectSlugTakenError()


# # ── CRUD ──────────────────────────────────────────────────────────────────────

# async def get_project_by_id(
#     db: AsyncSession, project_id: uuid.UUID
# ) -> Optional[Project]:
#     result = await db.execute(
#         select(Project).where(Project.id == project_id)
#     )
#     return result.scalar_one_or_none()


# async def get_default_project_for_user(
#     db: AsyncSession, user_id: uuid.UUID
# ) -> Optional[Project]:
#     result = await db.execute(
#         select(Project).where(
#             Project.owner_user_id == user_id,
#             Project.is_default == True,  # noqa: E712
#         )
#     )
#     return result.scalar_one_or_none()


# async def get_project_count_for_user(
#     db: AsyncSession, user_id: uuid.UUID
# ) -> int:
#     result = await db.execute(
#         select(func.count(Project.id)).where(Project.owner_user_id == user_id)
#     )
#     return result.scalar_one()


# async def create_project(
#     db: AsyncSession,
#     owner_user_id: uuid.UUID,
#     data: CreateProjectRequest,
#     is_default: bool = False,
# ) -> Project:
#     """
#     Create a project. Handles slug collision via IntegrityError catch —
#     the DB unique index is the actual guarantee, _unique_slug is optimistic.
#     """
#     base_slug = _slugify(data.name)
#     slug = await _unique_slug(db, base_slug, owner_user_id, None)

#     project = Project(
#         owner_user_id=owner_user_id,
#         owner_org_id=None,
#         name=data.name,
#         slug=slug,
#         description=data.description,
#         color=data.color,
#         is_default=is_default,
#         is_active=True,
#     )
#     db.add(project)
#     try:
#         await db.flush()
#     except IntegrityError:
#         await db.rollback()
#         # Concurrent insert with same slug — retry with suffix
#         slug = await _unique_slug(db, base_slug + "-2", owner_user_id, None)
#         project.slug = slug
#         db.add(project)
#         await db.flush()
#     return project


# async def create_default_project(
#     db: AsyncSession, owner_user_id: uuid.UUID
# ) -> Project:
#     """Create the auto Personal project for a new user."""
#     from app.schemas.project import CreateProjectRequest as CPR
#     data = CPR(name="Personal", description="Your default personal project")
#     return await create_project(db, owner_user_id, data, is_default=True)


# async def update_project(
#     db: AsyncSession,
#     project: Project,
#     data: UpdateProjectRequest,
# ) -> Project:
#     if data.name is not None and data.name != project.name:
#         base_slug = _slugify(data.name)
#         project.slug = await _unique_slug(
#             db, base_slug, project.owner_user_id, project.owner_org_id,
#             exclude_project_id=project.id,
#         )
#         project.name = data.name
#     if data.description is not None:
#         project.description = data.description
#     if data.color is not None:
#         project.color = data.color
#     if data.is_active is not None:
#         project.is_active = data.is_active
#     project.updated_at = datetime.now(timezone.utc)
#     db.add(project)
#     await db.flush()
#     return project


# async def delete_project(db: AsyncSession, project: Project) -> None:
#     await db.delete(project)
#     await db.flush()


# async def get_link_count_for_project(
#     db: AsyncSession, project_id: uuid.UUID
# ) -> int:
#     result = await db.execute(
#         select(func.count(Link.id)).where(Link.project_id == project_id)
#     )
#     return result.scalar_one()


# # ── Project list with click aggregates ───────────────────────────────────────

# async def get_projects_for_user(
#     db: AsyncSession,
#     user_id: uuid.UUID,
#     page: int = 1,
#     per_page: int = 20,
# ) -> tuple[list[dict], int]:
#     """
#     Return projects with pre-aggregated link_count, total_clicks,
#     clicks_this_month. Uses a single batch query per stat — no N+1.
#     """
#     from datetime import timedelta
#     offset = (page - 1) * per_page

#     # Total count
#     count_result = await db.execute(
#         select(func.count(Project.id)).where(Project.owner_user_id == user_id)
#     )
#     total = count_result.scalar_one()

#     # Projects page
#     proj_result = await db.execute(
#         select(Project)
#         .where(Project.owner_user_id == user_id)
#         .order_by(Project.is_default.desc(), Project.created_at.asc())
#         .offset(offset)
#         .limit(per_page)
#     )
#     projects = list(proj_result.scalars().all())
#     if not projects:
#         return [], total

#     project_ids = [p.id for p in projects]
#     now = datetime.now(timezone.utc)
#     month_start = now - timedelta(days=30)

#     # Batch: link count per project
#     link_counts_result = await db.execute(
#         select(Link.project_id, func.count(Link.id).label("cnt"))
#         .where(Link.project_id.in_(project_ids))
#         .group_by(Link.project_id)
#     )
#     link_counts = {row.project_id: row.cnt for row in link_counts_result.all()}

#     # Batch: total clicks and monthly clicks per project — one query
#     click_stats_result = await db.execute(
#         select(
#             Link.project_id,
#             func.count(LinkClick.id).label("total_clicks"),
#             func.count(
#                 case((LinkClick.clicked_at >= month_start, LinkClick.id))
#             ).label("clicks_this_month"),
#         )
#         .join(LinkClick, LinkClick.link_id == Link.id, isouter=True)
#         .where(Link.project_id.in_(project_ids))
#         .group_by(Link.project_id)
#     )
#     click_stats = {
#         row.project_id: {
#             "total_clicks": row.total_clicks,
#             "clicks_this_month": row.clicks_this_month,
#         }
#         for row in click_stats_result.all()
#     }

#     enriched = []
#     for p in projects:
#         stats = click_stats.get(p.id, {"total_clicks": 0, "clicks_this_month": 0})
#         enriched.append({
#             "project": p,
#             "link_count": link_counts.get(p.id, 0),
#             "total_clicks": stats["total_clicks"],
#             "clicks_this_month": stats["clicks_this_month"],
#         })

#     return enriched, total


# # ── Project analytics ─────────────────────────────────────────────────────────

# async def get_project_analytics(
#     db: AsyncSession, project_id: uuid.UUID
# ) -> dict:
#     """
#     Aggregate analytics across all links in the project.
#     Uses asyncio.gather to run independent queries concurrently.
#     """
#     import asyncio
#     from datetime import timedelta

#     now = datetime.now(timezone.utc)
#     today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
#     week_start = now - timedelta(days=7)
#     month_start = now - timedelta(days=30)

#     # Subquery: link IDs in this project
#     link_ids_subq = select(Link.id).where(Link.project_id == project_id).scalar_subquery()

#     # Helper: execute a query and return the result
#     async def run(q):
#         return await db.execute(q)

#     # All independent queries run concurrently
#     (
#         link_counts_r,
#         counts_r,
#         device_r,
#         browser_r,
#         os_r,
#         referer_r,
#         timeline_r,
#         peak_r,
#         bot_r,
#         top_links_r,
#     ) = await asyncio.gather(
#         # 1. Link counts
#         run(select(
#             func.count(Link.id).label("total"),
#             func.count(case((Link.is_active == True, Link.id))).label("active"),  # noqa: E712
#         ).where(Link.project_id == project_id)),

#         # 2. Click time-range counts
#         run(select(
#             func.count(LinkClick.id).label("total_clicks"),
#             func.count(case((LinkClick.clicked_at >= today_start, LinkClick.id))).label("clicks_today"),
#             func.count(case((LinkClick.clicked_at >= week_start, LinkClick.id))).label("clicks_this_week"),
#             func.count(case((LinkClick.clicked_at >= month_start, LinkClick.id))).label("clicks_this_month"),
#             func.count(func.distinct(LinkClick.ip_address)).label("unique_visitors"),
#         ).where(LinkClick.link_id.in_(link_ids_subq))),

#         # 3. Device breakdown
#         run(select(LinkClick.device_type, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id.in_(link_ids_subq))
#             .where(LinkClick.device_type.isnot(None))
#             .group_by(LinkClick.device_type)
#             .order_by(func.count(LinkClick.id).desc())),

#         # 4. Browser breakdown (top 10, no bots)
#         run(select(LinkClick.browser, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id.in_(link_ids_subq))
#             .where(LinkClick.browser.isnot(None))
#             .where(LinkClick.browser.notin_(["bot", "unknown"]))
#             .group_by(LinkClick.browser)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(10)),

#         # 5. OS breakdown (top 10, no bots)
#         run(select(LinkClick.os, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id.in_(link_ids_subq))
#             .where(LinkClick.os.isnot(None))
#             .where(LinkClick.os.notin_(["bot", "unknown"]))
#             .group_by(LinkClick.os)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(10)),

#         # 6. Referers (top 10)
#         run(select(LinkClick.referer, func.count(LinkClick.id).label("cnt"))
#             .where(LinkClick.link_id.in_(link_ids_subq))
#             .where(LinkClick.referer.isnot(None))
#             .group_by(LinkClick.referer)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(10)),

#         # 7. Timeline — last 30 days
#         run(select(
#             func.date(LinkClick.clicked_at).label("day"),
#             func.count(LinkClick.id).label("cnt"),
#         )
#             .where(LinkClick.link_id.in_(link_ids_subq))
#             .where(LinkClick.clicked_at >= month_start)
#             .group_by(func.date(LinkClick.clicked_at))
#             .order_by(func.date(LinkClick.clicked_at))),

#         # 8. Peak hour
#         run(select(
#             func.extract("hour", LinkClick.clicked_at).label("hour"),
#             func.count(LinkClick.id).label("cnt"),
#         )
#             .where(LinkClick.link_id.in_(link_ids_subq))
#             .group_by(func.extract("hour", LinkClick.clicked_at))
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(1)),

#         # 9. Bot vs human split
#         run(select(
#             func.count(case((LinkClick.device_type == "bot", LinkClick.id))).label("bot_clicks"),
#             func.count(case((LinkClick.device_type != "bot", LinkClick.id))).label("human_clicks"),
#         ).where(LinkClick.link_id.in_(link_ids_subq))),

#         # 10. Top 5 links in project
#         run(select(
#             Link.id,
#             Link.short_code,
#             Link.title,
#             func.count(LinkClick.id).label("clicks"),
#         )
#             .join(LinkClick, LinkClick.link_id == Link.id, isouter=True)
#             .where(Link.project_id == project_id)
#             .group_by(Link.id, Link.short_code, Link.title)
#             .order_by(func.count(LinkClick.id).desc())
#             .limit(5)),
#     )

#     link_counts_row = link_counts_r.one()
#     counts = counts_r.one()
#     peak_row = peak_r.first()

#     return {
#         "total_links": link_counts_row.total,
#         "active_links": link_counts_row.active,
#         "total_clicks": counts.total_clicks,
#         "unique_visitors": counts.unique_visitors,
#         "clicks_today": counts.clicks_today,
#         "clicks_this_week": counts.clicks_this_week,
#         "clicks_this_month": counts.clicks_this_month,
#         "top_links": [
#             {
#                 "link_id": str(r.id),
#                 "short_code": r.short_code,
#                 "title": r.title,
#                 "clicks": r.clicks,
#             }
#             for r in top_links_r.all()
#         ],
#         "devices": {r.device_type: r.cnt for r in device_r.all()},
#         "browsers": {r.browser: r.cnt for r in browser_r.all()},
#         "os_breakdown": {r.os: r.cnt for r in os_r.all()},
#         "referers": {r.referer: r.cnt for r in referer_r.all()},
#         "clicks_over_time": [
#             {"date": str(r.day), "clicks": r.cnt} for r in timeline_r.all()
#         ],
#         "peak_hour": int(peak_row.hour) if peak_row else None,
#         "bot_clicks": bot_r.one().bot_clicks,
#         "human_clicks": bot_r.one().human_clicks,
#     }
