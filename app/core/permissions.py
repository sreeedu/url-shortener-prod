"""
Permission layer — single place for all access control decisions.

Phase 1: ownership-only checks (project.owner_user_id == user.id).
Phase 3: each function gains an extra branch checking org membership
         and project roles. The router code never changes — it always
         calls the same functions and the logic inside evolves.

Design: load_project_context() fetches the project once and returns a
context object. All permission assertions receive the context — one DB
call per request regardless of how many checks are made.
"""
from dataclasses import dataclass, field
from typing import Optional
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.core.exceptions import ProjectNotFoundError, DefaultProjectError


@dataclass
class ProjectPermissionContext:
    project: Project
    user: User
    # Phase 3 will populate these from org_members and project_members tables.
    # Keeping them here now means the function signatures never change.
    org_role: Optional[str] = field(default=None)
    project_role: Optional[str] = field(default=None)


async def load_project_context(
    db: AsyncSession,
    project_id: uuid.UUID,
    user: User,
) -> ProjectPermissionContext:
    """
    Load project and verify the user can see it at all.
    Returns a context object for subsequent permission checks.

    Always raises ProjectNotFoundError for both "doesn't exist" and "not owner"
    — never reveals that a project exists to someone who doesn't own it.
    """
    from app.crud.project import get_project_by_id
    project = await get_project_by_id(db, project_id)

    if not project:
        raise ProjectNotFoundError()

    # Phase 1: direct ownership check
    if project.owner_user_id != user.id:
        # Return 404 not 403 — never confirm the project exists to non-owners
        raise ProjectNotFoundError()

    # Phase 3: add org membership check here
    # if project.owner_org_id:
    #     org_role = await get_org_role(db, project.owner_org_id, user.id)
    #     if not org_role:
    #         raise ProjectNotFoundError()
    #     project_role = await get_project_role(db, project.id, user.id)
    #     return ProjectPermissionContext(project, user, org_role, project_role)

    return ProjectPermissionContext(project=project, user=user)


# ── Permission assertions ────────────────────────────────────────────────────
# Each raises the appropriate exception or returns silently.
# Phase 3 adds org/project role checks inside each function body.

def assert_can_view_project(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner always. Phase 3: + org viewer, project viewer."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()


def assert_can_edit_project(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner always. Phase 3: + org admin, project manager."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()


def assert_can_delete_project(ctx: ProjectPermissionContext) -> None:
    """Only owner can delete. Default project can never be deleted."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()
    if ctx.project.is_default:
        raise DefaultProjectError()


def assert_can_create_link(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner + project must be active. Phase 3: + editor role."""
    from app.core.exceptions import ProjectInactiveError
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()
    if not ctx.project.is_active:
        raise ProjectInactiveError()


def assert_can_view_link(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner. Phase 3: + org viewer, project viewer."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()


def assert_can_edit_link(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner. Phase 3: + project editor."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()


def assert_can_delete_link(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner. Phase 3: + project manager."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()


def assert_can_view_analytics(ctx: ProjectPermissionContext) -> None:
    """Phase 1: owner. Phase 3: + analyst role."""
    if ctx.project.owner_user_id != ctx.user.id:
        raise ProjectNotFoundError()
