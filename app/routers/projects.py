from fastapi import APIRouter, Depends, Response, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.database import get_db
from app.core.config import settings
from app.core.exceptions import DefaultProjectError, ProjectLimitExceededError
from app.core.limiter import limiter
from app.core.permissions import (
    load_project_context,
    assert_can_edit_project,
    assert_can_delete_project,
    assert_can_view_analytics,
)
from app.crud.project import (
    get_project_count_for_user,
    create_project,
    get_projects_for_user,
    get_project_by_id,
    get_link_count_for_project,
    update_project,
    delete_project,
    get_project_analytics,
)
from app.crud.audit_log import write_audit_log_background, AuditAction
from app.schemas.project import (
    CreateProjectRequest, UpdateProjectRequest,
    ProjectResponse, ProjectListResponse, ProjectAnalyticsResponse,
)
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/projects", tags=["Projects"])


def _build_project_response(
    project,
    link_count: int = 0,
    total_clicks: int = 0,
    clicks_this_month: int = 0,
) -> ProjectResponse:
    return ProjectResponse(
        id=str(project.id),
        name=project.name,
        slug=project.slug,
        description=project.description,
        color=project.color,
        is_default=project.is_default,
        is_active=project.is_active,
        link_count=link_count,
        total_clicks=total_clicks,
        clicks_this_month=clicks_this_month,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


@router.post("", response_model=ProjectResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_CREATE_URL)
async def create_new_project(
    request: Request,
    payload: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await get_project_count_for_user(db, current_user.id)
    if count >= settings.MAX_PROJECTS_PER_USER:
        raise ProjectLimitExceededError()

    project = await create_project(db, current_user.id, payload)

    write_audit_log_background(
        action=AuditAction.PROJECT_CREATED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="project",
        target_id=project.id,
        metadata={"name": project.name, "slug": project.slug},
        ip_address=request.client.host if request.client else None,
    )

    return _build_project_response(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enriched, total = await get_projects_for_user(db, current_user.id, page, per_page)
    return ProjectListResponse(
        projects=[
            _build_project_response(
                e["project"],
                link_count=e["link_count"],
                total_clicks=e["total_clicks"],
                clicks_this_month=e["clicks_this_month"],
            )
            for e in enriched
        ],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    analytics = await get_project_analytics(db, ctx.project.id)
    return _build_project_response(
        ctx.project,
        link_count=analytics["total_links"],
        total_clicks=analytics["total_clicks"],
        clicks_this_month=analytics["clicks_this_month"],
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_existing_project(
    project_id: uuid.UUID,
    payload: UpdateProjectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_edit_project(ctx)

    # Default project cannot be deactivated
    if ctx.project.is_default and payload.is_active is False:
        raise DefaultProjectError()

    was_active = ctx.project.is_active
    project = await update_project(db, ctx.project, payload)

    # Determine audit action
    if payload.is_active is False and was_active:
        action = AuditAction.PROJECT_DEACTIVATED
    elif payload.is_active is True and not was_active:
        action = AuditAction.PROJECT_REACTIVATED
    else:
        action = AuditAction.PROJECT_UPDATED

    write_audit_log_background(
        action=action,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="project",
        target_id=project.id,
        metadata={"name": project.name},
        ip_address=request.client.host if request.client else None,
    )

    analytics = await get_project_analytics(db, project.id)
    return _build_project_response(
        project,
        link_count=analytics["total_links"],
        total_clicks=analytics["total_clicks"],
        clicks_this_month=analytics["clicks_this_month"],
    )


@router.delete("/{project_id}", status_code=204)
async def delete_existing_project(
    project_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_delete_project(ctx)  # raises DefaultProjectError if is_default

    # Require project to be empty — prevents accidental data loss
    from app.core.exceptions import ProjectNotEmptyError
    link_count = await get_link_count_for_project(db, ctx.project.id)
    if link_count > 0:
        raise ProjectNotEmptyError()

    write_audit_log_background(
        action=AuditAction.PROJECT_DELETED,
        actor_id=current_user.id,
        actor_email=current_user.email,
        target_type="project",
        target_id=ctx.project.id,
        metadata={"name": ctx.project.name, "slug": ctx.project.slug},
        ip_address=request.client.host if request.client else None,
    )

    await delete_project(db, ctx.project)
    return Response(status_code=204)


@router.get("/{project_id}/analytics", response_model=ProjectAnalyticsResponse)
async def get_project_stats(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ctx = await load_project_context(db, project_id, current_user)
    assert_can_view_analytics(ctx)

    analytics = await get_project_analytics(db, project_id)
    return ProjectAnalyticsResponse(
        project_id=str(ctx.project.id),
        project_name=ctx.project.name,
        **analytics,
    )

# from fastapi import APIRouter, Depends, Response, Query, Request
# from sqlalchemy.ext.asyncio import AsyncSession
# import uuid

# from app.core.database import get_db
# from app.core.config import settings
# from app.core.exceptions import DefaultProjectError, ProjectLimitExceededError
# from app.core.limiter import limiter
# from app.core.permissions import (
#     load_project_context,
#     assert_can_edit_project,
#     assert_can_delete_project,
#     assert_can_view_analytics,
# )
# from app.crud.project import (
#     get_project_count_for_user,
#     create_project,
#     get_projects_for_user,
#     get_project_by_id,
#     get_link_count_for_project,
#     update_project,
#     delete_project,
#     get_project_analytics,
# )
# from app.crud.audit_log import write_audit_log_background, AuditAction
# from app.schemas.project import (
#     CreateProjectRequest, UpdateProjectRequest,
#     ProjectResponse, ProjectListResponse, ProjectAnalyticsResponse,
# )
# from app.middleware.auth import get_current_user
# from app.models.user import User

# router = APIRouter(prefix="/api/projects", tags=["Projects"])


# def _build_project_response(
#     project,
#     link_count: int = 0,
#     total_clicks: int = 0,
#     clicks_this_month: int = 0,
# ) -> ProjectResponse:
#     return ProjectResponse(
#         id=str(project.id),
#         name=project.name,
#         slug=project.slug,
#         description=project.description,
#         color=project.color,
#         is_default=project.is_default,
#         is_active=project.is_active,
#         link_count=link_count,
#         total_clicks=total_clicks,
#         clicks_this_month=clicks_this_month,
#         created_at=project.created_at,
#         updated_at=project.updated_at,
#     )


# @router.post("", response_model=ProjectResponse, status_code=201)
# @limiter.limit("30/minute")
# async def create_new_project(
#     request: Request,
#     payload: CreateProjectRequest,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     count = await get_project_count_for_user(db, current_user.id)
#     if count >= settings.MAX_PROJECTS_PER_USER:
#         raise ProjectLimitExceededError()

#     project = await create_project(db, current_user.id, payload)

#     write_audit_log_background(
#         action=AuditAction.PROJECT_CREATED,
#         actor_id=current_user.id,
#         actor_email=current_user.email,
#         target_type="project",
#         target_id=project.id,
#         metadata={"name": project.name, "slug": project.slug},
#         ip_address=request.client.host if request.client else None,
#     )

#     return _build_project_response(project)


# @router.get("", response_model=ProjectListResponse)
# async def list_projects(
#     page: int = Query(1, ge=1),
#     per_page: int = Query(20, ge=1, le=100),
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     enriched, total = await get_projects_for_user(db, current_user.id, page, per_page)
#     return ProjectListResponse(
#         projects=[
#             _build_project_response(
#                 e["project"],
#                 link_count=e["link_count"],
#                 total_clicks=e["total_clicks"],
#                 clicks_this_month=e["clicks_this_month"],
#             )
#             for e in enriched
#         ],
#         total=total,
#         page=page,
#         per_page=per_page,
#     )


# @router.get("/{project_id}", response_model=ProjectResponse)
# async def get_project(
#     project_id: uuid.UUID,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     ctx = await load_project_context(db, project_id, current_user)
#     link_count = await get_link_count_for_project(db, ctx.project.id)
#     return _build_project_response(ctx.project, link_count=link_count)


# @router.patch("/{project_id}", response_model=ProjectResponse)
# async def update_existing_project(
#     project_id: uuid.UUID,
#     payload: UpdateProjectRequest,
#     request: Request,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     ctx = await load_project_context(db, project_id, current_user)
#     assert_can_edit_project(ctx)

#     # Default project cannot be deactivated
#     if ctx.project.is_default and payload.is_active is False:
#         raise DefaultProjectError()

#     was_active = ctx.project.is_active
#     project = await update_project(db, ctx.project, payload)

#     # Determine audit action
#     if payload.is_active is False and was_active:
#         action = AuditAction.PROJECT_DEACTIVATED
#     elif payload.is_active is True and not was_active:
#         action = AuditAction.PROJECT_REACTIVATED
#     else:
#         action = AuditAction.PROJECT_UPDATED

#     write_audit_log_background(
#         action=action,
#         actor_id=current_user.id,
#         actor_email=current_user.email,
#         target_type="project",
#         target_id=project.id,
#         metadata={"name": project.name},
#         ip_address=request.client.host if request.client else None,
#     )

#     link_count = await get_link_count_for_project(db, project.id)
#     return _build_project_response(project, link_count=link_count)


# @router.delete("/{project_id}", status_code=204)
# async def delete_existing_project(
#     project_id: uuid.UUID,
#     request: Request,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     ctx = await load_project_context(db, project_id, current_user)
#     assert_can_delete_project(ctx)  # raises DefaultProjectError if is_default

#     # Require project to be empty — prevents accidental data loss
#     from app.core.exceptions import ProjectNotEmptyError
#     link_count = await get_link_count_for_project(db, ctx.project.id)
#     if link_count > 0:
#         raise ProjectNotEmptyError()

#     write_audit_log_background(
#         action=AuditAction.PROJECT_DELETED,
#         actor_id=current_user.id,
#         actor_email=current_user.email,
#         target_type="project",
#         target_id=ctx.project.id,
#         metadata={"name": ctx.project.name, "slug": ctx.project.slug},
#         ip_address=request.client.host if request.client else None,
#     )

#     await delete_project(db, ctx.project)
#     return Response(status_code=204)


# @router.get("/{project_id}/analytics", response_model=ProjectAnalyticsResponse)
# async def get_project_stats(
#     project_id: uuid.UUID,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(get_current_user),
# ):
#     ctx = await load_project_context(db, project_id, current_user)
#     assert_can_view_analytics(ctx)

#     analytics = await get_project_analytics(db, project_id)
#     return ProjectAnalyticsResponse(
#         project_id=str(ctx.project.id),
#         project_name=ctx.project.name,
#         **analytics,
#     )
