from fastapi import APIRouter, Depends, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.core.database import get_db
from app.core.security import (
    verify_password, get_dummy_hash,
    create_access_token, create_refresh_token,
    decode_token, generate_reset_token, hash_reset_token,
)
from app.core.mailer import send_password_reset_email
from app.core.exceptions import (
    InvalidCredentialsError, UserAlreadyExistsError,
    ResetTokenInvalidError, InvalidTokenError,
)
from app.core.limiter import limiter
from app.core.config import settings
from app.crud.user import get_user_by_email, create_user, update_password, update_last_login, get_user_by_id
from app.crud.password_reset import create_reset_token, get_valid_reset_token, mark_token_used
from app.crud.project import create_default_project
from app.crud.audit_log import write_audit_log_background, AuditAction
from app.schemas.auth import (
    SignupRequest, LoginRequest, TokenResponse,
    RefreshRequest, ForgotPasswordRequest, ResetPasswordRequest, UserResponse,
)
from app.middleware.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=UserResponse, status_code=201)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def signup(
    request: Request,
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db),
):
    existing = await get_user_by_email(db, payload.email)
    if existing:
        raise UserAlreadyExistsError()

    user = await create_user(db, payload.email, payload.password)

    # Auto-create the Personal default project for every new user
    await create_default_project(db, user.id)

    write_audit_log_background(
        action=AuditAction.USER_SIGNED_UP,
        actor_id=user.id,
        actor_email=user.email,
        target_type="user",
        target_id=user.id,
        ip_address=request.client.host if request.client else None,
    )

    return UserResponse(
        id=str(user.id),
        email=user.email,
        is_verified=user.is_verified,
        created_at=user.created_at.isoformat(),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_email(db, payload.email)
    password_ok = verify_password(
        payload.password,
        user.password_hash if user else get_dummy_hash(),
    )
    if not user or not password_ok or not user.is_active:
        raise InvalidCredentialsError()

    await update_last_login(db, user)

    write_audit_log_background(
        action=AuditAction.USER_LOGGED_IN,
        actor_id=user.id,
        actor_email=user.email,
        target_type="user",
        target_id=user.id,
        ip_address=request.client.host if request.client else None,
    )

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(
    request: Request,
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_db),
):
    user_id_str = decode_token(payload.refresh_token, token_type="refresh")
    if not user_id_str:
        raise InvalidTokenError()

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise InvalidTokenError()

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise InvalidTokenError()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/forgot-password", status_code=202)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await get_user_by_email(db, payload.email)
    if user and user.is_active:
        raw_token, token_hash = generate_reset_token()
        await create_reset_token(db, user.id, token_hash)
        background_tasks.add_task(send_password_reset_email, user.email, raw_token)
        write_audit_log_background(
            action=AuditAction.USER_PASSWORD_RESET_REQUESTED,
            actor_id=user.id,
            actor_email=user.email,
            target_type="user",
            target_id=user.id,
            ip_address=request.client.host if request.client else None,
        )
    return {"message": "If an account with that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=200)
@limiter.limit(settings.RATE_LIMIT_AUTH)
async def reset_password(
    request: Request,
    payload: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    token_hash = hash_reset_token(payload.token)
    reset_token = await get_valid_reset_token(db, token_hash)
    if not reset_token:
        raise ResetTokenInvalidError()
    await mark_token_used(db, reset_token)
    await update_password(db, reset_token.user, payload.new_password)
    write_audit_log_background(
        action=AuditAction.USER_PASSWORD_RESET_COMPLETED,
        actor_id=reset_token.user.id,
        actor_email=reset_token.user.email,
        target_type="user",
        target_id=reset_token.user.id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": "Password updated successfully. Please log in with your new password."}


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at.isoformat(),
    )
