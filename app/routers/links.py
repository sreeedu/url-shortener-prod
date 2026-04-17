from fastapi import APIRouter, Depends, Response, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.database import get_db
from app.core.config import settings
from app.core.exceptions import LinkNotFoundError, ShortCodeTakenError, LinkLimitExceededError
from app.core.limiter import limiter
from app.core.redis import get_redis_or_none, url_cache_key, url_id_cache_key
from app.core.permissions import (
    load_project_context,
    assert_can_create_link,
    assert_can_view_link,
    assert_can_edit_link,
    assert_can_delete_link,
    assert_can_view_analytics,
)
from app.crud.link import (
    get_link_by_id,
    create_link,
    get_links_for_project,
    update_link,
    delete_link,
    get_click_count,
    get_link_count_for_user,
    get_link_count_for_project,
    short_code_exists,
    get_link_analytics,
)
from app.crud.audit_log import write_audit_log_background, AuditAction
from app.schemas.link import (
    CreateLinkRequest, UpdateLinkRequest,
    LinkResponse, LinkListResponse, LinkAnalyticsResponse,
)
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/projects/{project_id}/links", tags=["Links"])


def _build_link_response(link, click_count: int) -> LinkResponse:
    from app.core.config import settings as s
    return LinkResponse(
        id=str(link.id),
        project_id=str(link.project_id),
        short_code=link.short_code,
        short_url=f"{s.BASE_URL}/{link.short_code}",
        original_url=link.original_url,
        title=link.title,
        expires_at=link.expires_at,
        is_active=link.is_active,
        click_count=click_count,
        created_at=link.created_at,
        updated_at=link.updated_at,
    )


@router.post("", response_model=LinkResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_CREATE_URL)
async def create_new_link(
    project_id: uuid.UUID,
    payload: CreateLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_create_link(ctx)  # also checks project.is_active

    # Enforce per-project link cap
    project_link_count = await get_link_count_for_project(db, project_id)
    if project_link_count >= settings.MAX_LINKS_PER_PROJECT:
        raise LinkLimitExceededError(scope="project")

    # Enforce per-user total link cap
    user_link_count = await get_link_count_for_user(db, current_user.id)
    if user_link_count >= settings.MAX_LINKS_PER_USER:
        raise LinkLimitExceededError(scope="account")

    # Custom code uniqueness check
    if payload.custom_code and await short_code_exists(db, payload.custom_code):
        raise ShortCodeTakenError()

    link = await create_link(db, project_id, current_user.id, payload)

    write_audit_log_background(
        action=AuditAction.LINK_CREATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="link",
        target_id=link.id,
        metadata={"short_code": link.short_code, "project_id": str(project_id)},
        ip_address=request.client.host if request.client else None,
    )

    return _build_link_response(link, 0)


@router.get("", response_model=LinkListResponse)
async def list_project_links(
    project_id: uuid.UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    enriched, total = await get_links_for_project(db, project_id, page, per_page)
    return LinkListResponse(
        links=[
            _build_link_response(e["link"], e["click_count"])
            for e in enriched
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{link_id}", response_model=LinkResponse)
async def get_link(
    project_id: uuid.UUID,
    link_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_view_link(ctx)

    link = await get_link_by_id(db, link_id)
    if not link or link.project_id != project_id:
        raise LinkNotFoundError()

    count = await get_click_count(db, link.id)
    return _build_link_response(link, count)


@router.patch("/{link_id}", response_model=LinkResponse)
async def update_existing_link(
    project_id: uuid.UUID,
    link_id: uuid.UUID,
    payload: UpdateLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_edit_link(ctx)

    link = await get_link_by_id(db, link_id)
    if not link or link.project_id != project_id:
        raise LinkNotFoundError()

    was_active = link.is_active
    updated = await update_link(db, link, payload)

    # Invalidate Redis cache on any is_active change
    if payload.is_active is not None:
        redis = await get_redis_or_none()
        if redis:
            try:
                await redis.delete(url_cache_key(link.short_code))
                await redis.delete(url_id_cache_key(link.short_code))
            except Exception:
                pass

    # Determine correct audit action
    if payload.is_active is False and was_active:
        action = AuditAction.LINK_DEACTIVATED
    elif payload.is_active is True and not was_active:
        action = AuditAction.LINK_REACTIVATED
    else:
        action = AuditAction.LINK_UPDATED

    write_audit_log_background(
        action=action,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="link",
        target_id=link.id,
        metadata={"short_code": link.short_code},
        ip_address=request.client.host if request.client else None,
    )

    count = await get_click_count(db, updated.id)
    return _build_link_response(updated, count)


@router.delete("/{link_id}", status_code=204)
async def delete_existing_link(
    project_id: uuid.UUID,
    link_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_delete_link(ctx)

    link = await get_link_by_id(db, link_id)
    if not link or link.project_id != project_id:
        raise LinkNotFoundError()

    # Evict from Redis before deleting
    redis = await get_redis_or_none()
    if redis:
        try:
            await redis.delete(url_cache_key(link.short_code))
            await redis.delete(url_id_cache_key(link.short_code))
        except Exception:
            pass

    write_audit_log_background(
        action=AuditAction.LINK_DELETED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="link",
        target_id=link.id,
        metadata={"short_code": link.short_code, "project_id": str(project_id)},
        ip_address=request.client.host if request.client else None,
    )

    await delete_link(db, link)
    return Response(status_code=204)


@router.get("/{link_id}/analytics", response_model=LinkAnalyticsResponse)
async def get_link_stats(
    project_id: uuid.UUID,
    link_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_view_analytics(ctx)

    link = await get_link_by_id(db, link_id)
    if not link or link.project_id != project_id:
        raise LinkNotFoundError()

    analytics = await get_link_analytics(db, link_id)
    return LinkAnalyticsResponse(
        link_id=str(link.id),
        short_code=link.short_code,
        **analytics,
    )
