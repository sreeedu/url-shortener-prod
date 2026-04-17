from fastapi import APIRouter, Depends, Query, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case, text
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from app.core.database import get_db
from app.core.config import settings
from app.core.limiter import limiter
from app.core.exceptions import SelfDeactivationError
from app.middleware.auth import get_platform_admin, get_current_user
from app.models.user import User
from app.models.project import Project
from app.models.link import Link, LinkClick
from app.crud.audit_log import write_audit_log, get_audit_logs, AuditAction
from app.schemas.platform import (
    PlatformUserResponse, PlatformUserListResponse,
    PlatformProjectResponse, PlatformProjectListResponse,
    PlatformLinkResponse, PlatformLinkListResponse,
    PlatformStatsResponse, AuditLogResponse, AuditLogListResponse,
    ClicksPerDay, AdminInviteRequest, AdminAcceptRequest,
)

router = APIRouter(prefix="/api/platform", tags=["Platform Admin"])


# ── Platform stats ────────────────────────────────────────────────────────────

@router.get("/stats", response_model=PlatformStatsResponse)
@limiter.limit(settings.RATE_LIMIT_PLATFORM_READ)
async def platform_stats(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_platform_admin),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)

    # Users
    user_stats = await db.execute(select(
        func.count(User.id).label("total"),
        func.count(case((User.created_at >= today_start, User.id))).label("today"),
        func.count(case((User.created_at >= week_start, User.id))).label("week"),
        func.count(case((User.created_at >= month_start, User.id))).label("month"),
        func.count(case((User.last_login_at >= month_start, User.id))).label("active_30d"),
    ))
    u = user_stats.one()

    total_projects = (await db.execute(select(func.count(Project.id)))).scalar_one()
    total_links = (await db.execute(select(func.count(Link.id)))).scalar_one()

    # Clicks
    click_stats = await db.execute(select(
        func.count(LinkClick.id).label("total"),
        func.count(case((LinkClick.clicked_at >= today_start, LinkClick.id))).label("today"),
        func.count(case((LinkClick.clicked_at >= week_start, LinkClick.id))).label("week"),
        func.count(case((LinkClick.device_type == "bot", LinkClick.id))).label("bot"),
    ))
    c = click_stats.one()

    bot_pct = round((c.bot / c.total * 100), 2) if c.total > 0 else 0.0

    # 30-day click timeline
    timeline_result = await db.execute(
        select(
            func.date(LinkClick.clicked_at).label("day"),
            func.count(LinkClick.id).label("cnt"),
        )
        .where(LinkClick.clicked_at >= month_start)
        .group_by(func.date(LinkClick.clicked_at))
        .order_by(func.date(LinkClick.clicked_at))
    )

    return PlatformStatsResponse(
        total_users=u.total,
        signups_today=u.today,
        signups_this_week=u.week,
        signups_this_month=u.month,
        active_users_30d=u.active_30d,
        total_projects=total_projects,
        total_links=total_links,
        total_clicks=c.total,
        clicks_today=c.today,
        clicks_this_week=c.week,
        bot_percentage=bot_pct,
        clicks_over_time=[
            ClicksPerDay(date=str(r.day), clicks=r.cnt)
            for r in timeline_result.all()
        ],
    )


# ── Admin Invitation ──────────────────────────────────────────────────────────

@router.post("/admins/invite")
@limiter.limit(settings.RATE_LIMIT_PLATFORM_WRITE)
async def invite_admin(
    request: Request,
    payload: AdminInviteRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    from app.crud.user import get_user_by_email
    from app.core.exceptions import AppException
    from app.core.security import create_admin_invite_token
    from app.core.mailer import send_admin_invite_email, send_admin_invite_confirmation

    target_user = await get_user_by_email(db, payload.email)
    if not target_user:
        raise AppException(404, "User not found. They must sign up first.")
    if target_user.is_platform_admin:
        raise AppException(400, "User is already a platform admin.")
    
    raw_token = create_admin_invite_token(str(target_user.id), str(admin.id))
    
    background_tasks.add_task(send_admin_invite_email, target_user.email, admin.email, raw_token)
    background_tasks.add_task(send_admin_invite_confirmation, admin.email, target_user.email)
    
    await write_audit_log(
        db,
        action=AuditAction.PLATFORM_ADMIN_INVITED,
        actor_id=admin.id,
        actor_email=admin.email,
        target_type="user",
        target_id=target_user.id,
        metadata={"invited_email": target_user.email},
        ip_address=request.client.host if request.client else None,
    )
    
    return {"message": f"Invitation sent to {target_user.email}"}


@router.post("/admins/accept")
@limiter.limit(settings.RATE_LIMIT_PLATFORM_WRITE)
async def accept_admin_invite(
    request: Request,
    payload: AdminAcceptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.core.exceptions import AppException
    from app.core.security import decode_token

    subject = decode_token(payload.token, token_type="admin_invite")
    if not subject:
        raise AppException(400, "Invalid or expired invitation token.")
    
    if subject != str(current_user.id):
        raise AppException(403, "This invitation was sent to a different user.")
    
    if current_user.is_platform_admin:
        return {"message": "You are already a platform admin."}
        
    current_user.is_platform_admin = True
    db.add(current_user)
    
    await write_audit_log(
        db,
        action=AuditAction.PLATFORM_ADMIN_ACCEPTED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="user",
        target_id=current_user.id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": "You are now a platform admin."}


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users", response_model=PlatformUserListResponse)
@limiter.limit(settings.RATE_LIMIT_PLATFORM_READ)
async def list_users(
    request: Request,
    cursor: Optional[str] = Query(None),
    per_page: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_platform_admin),
):
    # Explicit column selection — never load password_hash in admin queries
    q = select(
        User.id, User.email, User.is_active, User.is_verified,
        User.is_platform_admin, User.created_at, User.last_login_at,
    ).order_by(User.created_at.desc())

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            q = q.where(User.created_at < cursor_dt)
        except ValueError:
            pass

    if search:
        q = q.where(User.email.ilike(f"%{search}%"))
    if is_active is not None:
        q = q.where(User.is_active == is_active)

    q = q.limit(per_page + 1)
    result = await db.execute(q)
    rows = result.all()

    next_cursor = None
    if len(rows) > per_page:
        rows = rows[:per_page]
        next_cursor = rows[-1].created_at.isoformat()

    # Total count (without cursor filter)
    total_q = select(func.count(User.id))
    if search:
        total_q = total_q.where(User.email.ilike(f"%{search}%"))
    if is_active is not None:
        total_q = total_q.where(User.is_active == is_active)
    total = (await db.execute(total_q)).scalar_one()

    # Batch project and link counts
    user_ids = [r.id for r in rows]
    proj_counts = {}
    link_counts = {}
    click_totals = {}

    if user_ids:
        pc = await db.execute(
            select(Project.owner_user_id, func.count(Project.id).label("cnt"))
            .where(Project.owner_user_id.in_(user_ids))
            .group_by(Project.owner_user_id)
        )
        proj_counts = {r.owner_user_id: r.cnt for r in pc.all()}

        lc = await db.execute(
            select(Link.created_by, func.count(Link.id).label("cnt"))
            .where(Link.created_by.in_(user_ids))
            .group_by(Link.created_by)
        )
        link_counts = {r.created_by: r.cnt for r in lc.all()}

        cl = await db.execute(
            select(Link.created_by, func.count(LinkClick.id).label("cnt"))
            .join(LinkClick, LinkClick.link_id == Link.id)
            .where(Link.created_by.in_(user_ids))
            .group_by(Link.created_by)
        )
        click_totals = {r.created_by: r.cnt for r in cl.all()}

    return PlatformUserListResponse(
        users=[
            PlatformUserResponse(
                id=str(r.id),
                email=r.email,
                is_active=r.is_active,
                is_verified=r.is_verified,
                is_platform_admin=r.is_platform_admin,
                project_count=proj_counts.get(r.id, 0),
                link_count=link_counts.get(r.id, 0),
                total_clicks=click_totals.get(r.id, 0),
                created_at=r.created_at,
                last_login_at=r.last_login_at,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
        total_count=total,
    )


@router.get("/users/{user_id}", response_model=PlatformUserResponse)
@limiter.limit(settings.RATE_LIMIT_PLATFORM_READ)
async def get_user_detail(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    from app.core.exceptions import UserNotFoundError

    result = await db.execute(
        select(
            User.id, User.email, User.is_active, User.is_verified,
            User.is_platform_admin, User.created_at, User.last_login_at,
        ).where(User.id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise UserNotFoundError()

    proj_count = (await db.execute(
        select(func.count(Project.id)).where(Project.owner_user_id == user_id)
    )).scalar_one()

    link_count = (await db.execute(
        select(func.count(Link.id)).where(Link.created_by == user_id)
    )).scalar_one()

    total_clicks = (await db.execute(
        select(func.count(LinkClick.id))
        .join(Link, Link.id == LinkClick.link_id)
        .where(Link.created_by == user_id)
    )).scalar_one()

    # Synchronous audit log — admin viewed a user profile
    await write_audit_log(
        db,
        action=AuditAction.PLATFORM_USER_VIEWED,
        actor_id=admin.id,
        actor_email=admin.email,
        target_type="user",
        target_id=user_id,
        ip_address=request.client.host if request.client else None,
    )

    return PlatformUserResponse(
        id=str(row.id),
        email=row.email,
        is_active=row.is_active,
        is_verified=row.is_verified,
        is_platform_admin=row.is_platform_admin,
        project_count=proj_count,
        link_count=link_count,
        total_clicks=total_clicks,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


@router.patch("/users/{user_id}/deactivate")
@limiter.limit(settings.RATE_LIMIT_PLATFORM_WRITE)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    from app.core.exceptions import UserNotFoundError
    from app.crud.user import get_user_by_id

    if user_id == admin.id:
        raise SelfDeactivationError()

    user = await get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError()

    if not user.is_active:
        return {"message": "User is already deactivated", "user_id": str(user_id)}

    user.is_active = False
    db.add(user)

    # Synchronous — if audit write fails, deactivation does not happen
    await write_audit_log(
        db,
        action=AuditAction.PLATFORM_USER_DEACTIVATED,
        actor_id=admin.id,
        actor_email=admin.email,
        target_type="user",
        target_id=user_id,
        metadata={"email": user.email},
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "User deactivated", "user_id": str(user_id)}


@router.patch("/users/{user_id}/reactivate")
@limiter.limit(settings.RATE_LIMIT_PLATFORM_WRITE)
async def reactivate_user(
    user_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    from app.core.exceptions import UserNotFoundError
    from app.crud.user import get_user_by_id

    user = await get_user_by_id(db, user_id)
    if not user:
        raise UserNotFoundError()

    if user.is_active:
        return {"message": "User is already active", "user_id": str(user_id)}

    user.is_active = True
    db.add(user)

    await write_audit_log(
        db,
        action=AuditAction.PLATFORM_USER_REACTIVATED,
        actor_id=admin.id,
        actor_email=admin.email,
        target_type="user",
        target_id=user_id,
        metadata={"email": user.email},
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "User reactivated", "user_id": str(user_id)}


# ── Projects & Links (read-only admin views) ──────────────────────────────────

@router.get("/projects", response_model=PlatformProjectListResponse)
@limiter.limit(settings.RATE_LIMIT_PLATFORM_READ)
async def list_all_projects(
    request: Request,
    cursor: Optional[str] = Query(None),
    per_page: int = Query(50, ge=1, le=200),
    owner_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_platform_admin),
):
    q = (
        select(
            Project.id, Project.owner_user_id, Project.owner_org_id,
            Project.name, Project.slug, Project.is_default,
            Project.is_active, Project.created_at,
            User.email.label("owner_email")
        )
        .outerjoin(User, Project.owner_user_id == User.id)
        .order_by(Project.created_at.desc())
    )

    if cursor:
        try:
            q = q.where(Project.created_at < datetime.fromisoformat(cursor))
        except ValueError:
            pass
    if owner_id:
        q = q.where(Project.owner_user_id == owner_id)

    q = q.limit(per_page + 1)
    result = await db.execute(q)
    rows = result.all()

    next_cursor = None
    if len(rows) > per_page:
        rows = rows[:per_page]
        next_cursor = rows[-1].created_at.isoformat()

    project_ids = [r.id for r in rows]
    link_counts = {}
    if project_ids:
        lc = await db.execute(
            select(Link.project_id, func.count(Link.id).label("cnt"))
            .where(Link.project_id.in_(project_ids))
            .group_by(Link.project_id)
        )
        link_counts = {r.project_id: r.cnt for r in lc.all()}

    # Total count (without cursor filter) for consistent pagination UX
    total_q = select(func.count(Project.id))
    if owner_id:
        total_q = total_q.where(Project.owner_user_id == owner_id)
    total_count = (await db.execute(total_q)).scalar_one()

    return PlatformProjectListResponse(
        projects=[
            PlatformProjectResponse(
                id=str(r.id),
                owner_user_id=str(r.owner_user_id) if r.owner_user_id else None,
                owner_email=r.owner_email,
                owner_org_id=str(r.owner_org_id) if r.owner_org_id else None,
                name=r.name,
                slug=r.slug,
                is_default=r.is_default,
                is_active=r.is_active,
                link_count=link_counts.get(r.id, 0),
                created_at=r.created_at,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
        total_count=total_count,
    )


@router.get("/links", response_model=PlatformLinkListResponse)
@limiter.limit(settings.RATE_LIMIT_PLATFORM_READ)
async def list_all_links(
    request: Request,
    cursor: Optional[str] = Query(None),
    per_page: int = Query(50, ge=1, le=200),
    project_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_platform_admin),
):
    q = (
        select(
            Link.id, Link.project_id, Link.created_by,
            Link.short_code, Link.original_url, Link.title,
            Link.is_active, Link.created_at,
            User.email.label("created_by_email")
        )
        .outerjoin(User, Link.created_by == User.id)
        .order_by(Link.created_at.desc())
    )

    if cursor:
        try:
            q = q.where(Link.created_at < datetime.fromisoformat(cursor))
        except ValueError:
            pass
    if project_id:
        q = q.where(Link.project_id == project_id)

    q = q.limit(per_page + 1)
    result = await db.execute(q)
    rows = result.all()

    next_cursor = None
    if len(rows) > per_page:
        rows = rows[:per_page]
        next_cursor = rows[-1].created_at.isoformat()

    link_ids = [r.id for r in rows]
    click_counts = {}
    if link_ids:
        cc = await db.execute(
            select(LinkClick.link_id, func.count(LinkClick.id).label("cnt"))
            .where(LinkClick.link_id.in_(link_ids))
            .group_by(LinkClick.link_id)
        )
        click_counts = {r.link_id: r.cnt for r in cc.all()}

    # Total count (without cursor filter) for consistent pagination UX
    total_q = select(func.count(Link.id))
    if project_id:
        total_q = total_q.where(Link.project_id == project_id)
    total_count = (await db.execute(total_q)).scalar_one()

    return PlatformLinkListResponse(
        links=[
            PlatformLinkResponse(
                id=str(r.id),
                project_id=str(r.project_id),
                created_by=str(r.created_by),
                created_by_email=r.created_by_email,
                short_code=r.short_code,
                original_url=r.original_url,
                title=r.title,
                is_active=r.is_active,
                click_count=click_counts.get(r.id, 0),
                created_at=r.created_at,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
        total_count=total_count,
    )


# ── Audit logs ────────────────────────────────────────────────────────────────

@router.get("/audit-logs", response_model=AuditLogListResponse)
@limiter.limit(settings.RATE_LIMIT_PLATFORM_READ)
async def list_audit_logs(
    request: Request,
    cursor: Optional[str] = Query(None),
    per_page: int = Query(50, ge=1, le=200),
    actor_id: Optional[uuid.UUID] = Query(None),
    action: Optional[str] = Query(None),
    target_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_platform_admin),
):
    logs, next_cursor = await get_audit_logs(
        db,
        cursor=cursor,
        per_page=per_page,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
    )
    return AuditLogListResponse(
        logs=[
            AuditLogResponse(
                id=str(log.id),
                actor_id=str(log.actor_id) if log.actor_id else None,
                actor_email=log.actor_email,
                action=log.action,
                target_type=log.target_type,
                target_id=str(log.target_id) if log.target_id else None,
                metadata=log.meta_data,
                ip_address=log.ip_address,
                created_at=log.created_at,
            )
            for log in logs
        ],
        next_cursor=next_cursor,
    )
