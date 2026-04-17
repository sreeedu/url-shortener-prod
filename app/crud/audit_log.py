import uuid
import asyncio
import logging
from typing import Optional, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# ── Action constants ──────────────────────────────────────────────────────────
# All valid audit actions defined here — never use raw strings in routers.

class AuditAction:
    # Auth
    USER_SIGNED_UP = "user.signed_up"
    USER_LOGGED_IN = "user.logged_in"
    USER_PASSWORD_RESET_REQUESTED = "user.password_reset_requested"
    USER_PASSWORD_RESET_COMPLETED = "user.password_reset_completed"
    USER_EMAIL_VERIFIED = "user.email_verified"

    # Projects
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DEACTIVATED = "project.deactivated"
    PROJECT_REACTIVATED = "project.reactivated"
    PROJECT_DELETED = "project.deleted"

    # Links
    LINK_CREATED = "link.created"
    LINK_UPDATED = "link.updated"
    LINK_DEACTIVATED = "link.deactivated"
    LINK_REACTIVATED = "link.reactivated"
    LINK_DELETED = "link.deleted"

    # Platform admin — written synchronously, failure aborts the operation
    PLATFORM_USER_VIEWED = "platform.user_viewed"
    PLATFORM_USER_DEACTIVATED = "platform.user_deactivated"
    PLATFORM_USER_REACTIVATED = "platform.user_reactivated"
    PLATFORM_ADMIN_INVITED = "platform.admin_invited"
    PLATFORM_ADMIN_ACCEPTED = "platform.admin_accepted"


# ── Write helpers ─────────────────────────────────────────────────────────────

async def write_audit_log(
    db: AsyncSession,
    action: str,
    actor_id: Optional[uuid.UUID] = None,
    actor_email: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[uuid.UUID] = None,
    metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Synchronous audit write — used for security-critical events.
    Runs within the current request transaction.
    If this fails, the calling operation should also fail.
    """
    log = AuditLog(
        actor_id=actor_id,
        actor_email=actor_email,
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta_data=metadata,
        ip_address=ip_address,
    )
    db.add(log)
    await db.flush()


# Module-level set holds strong references to in-flight background tasks.
# Without this, asyncio may GC unreferenced tasks before they complete,
# silently dropping audit log writes under load.
_background_tasks: set[asyncio.Task] = set()


async def _write_audit_log_task(
    action: str,
    actor_id: Optional[uuid.UUID],
    actor_email: Optional[str],
    target_type: Optional[str],
    target_id: Optional[uuid.UUID],
    metadata: Optional[dict],
    ip_address: Optional[str],
) -> None:
    """Inner coroutine for fire-and-forget audit writes."""
    from app.core.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as session:
            log = AuditLog(
                actor_id=actor_id,
                actor_email=actor_email,
                action=action,
                target_type=target_type,
                target_id=target_id,
                meta_data=metadata,
                ip_address=ip_address,
            )
            session.add(log)
            await session.commit()
    except Exception as e:
        logger.warning(f"Failed to write audit log [{action}]: {e}")


def write_audit_log_background(
    action: str,
    actor_id: Optional[uuid.UUID] = None,
    actor_email: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[uuid.UUID] = None,
    metadata: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Fire-and-forget audit write for non-security-critical events.
    Creates an asyncio task — caller does not await.
    Failure is logged as a warning but does not affect the response.

    The task reference is stored in _background_tasks to prevent Python's
    garbage collector from cancelling it before it completes. The done-callback
    removes the reference once the task finishes.
    """
    task = asyncio.create_task(_write_audit_log_task(
        action=action,
        actor_id=actor_id,
        actor_email=actor_email,
        target_type=target_type,
        target_id=target_id,
        metadata=metadata,
        ip_address=ip_address,
    ))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


# ── Admin queries ─────────────────────────────────────────────────────────────

async def get_audit_logs(
    db: AsyncSession,
    cursor: Optional[str] = None,        # ISO datetime string
    per_page: int = 50,
    actor_id: Optional[uuid.UUID] = None,
    action: Optional[str] = None,
    target_type: Optional[str] = None,
) -> tuple[list[AuditLog], Optional[str]]:
    """
    Cursor-paginated audit log query, newest first.
    cursor = created_at of last item seen; next page returns older items.
    """
    from datetime import datetime, timezone

    q = select(AuditLog).order_by(AuditLog.created_at.desc())

    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            q = q.where(AuditLog.created_at < cursor_dt)
        except ValueError:
            pass  # invalid cursor — ignore and start from beginning

    if actor_id:
        q = q.where(AuditLog.actor_id == actor_id)
    if action:
        q = q.where(AuditLog.action == action)
    if target_type:
        q = q.where(AuditLog.target_type == target_type)

    q = q.limit(per_page + 1)  # fetch one extra to detect if there's a next page
    result = await db.execute(q)
    logs = list(result.scalars().all())

    next_cursor = None
    if len(logs) > per_page:
        logs = logs[:per_page]
        next_cursor = logs[-1].created_at.isoformat()

    return logs, next_cursor
