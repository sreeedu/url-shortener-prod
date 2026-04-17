from fastapi import HTTPException, status


class AppException(HTTPException):
    pass


# ── Auth ──────────────────────────────────────────────────────────────────────

class InvalidCredentialsError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

class UnverifiedEmailError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email not verified",
            headers={"WWW-Authenticate": "Bearer"},
        )

class TokenExpiredError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

class InvalidTokenError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or malformed token",
            headers={"WWW-Authenticate": "Bearer"},
        )

class UserNotFoundError(AppException):
    def __init__(self):
        super().__init__(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

class UserAlreadyExistsError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

class ResetTokenInvalidError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset link is invalid or has expired",
        )


# ── Projects ──────────────────────────────────────────────────────────────────

class ProjectNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

class DefaultProjectError(AppException):
    """Raised when trying to delete or deactivate the default Personal project."""
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The default Personal project cannot be deleted or deactivated",
        )

class ProjectLimitExceededError(AppException):
    def __init__(self):
        from app.core.config import settings
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Project limit reached. Maximum {settings.MAX_PROJECTS_PER_USER} projects per account.",
        )

class ProjectInactiveError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot create links in an inactive project",
        )

class ProjectSlugTakenError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="A project with this name already exists",
        )

class ProjectNotEmptyError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delete all links before deleting this project",
        )


# ── Links ─────────────────────────────────────────────────────────────────────

class LinkNotFoundError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short link not found",
        )

class LinkExpiredError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail="This short link has expired",
        )

class LinkInactiveError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail="This short link has been disabled",
        )

class ShortCodeTakenError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This custom short code is already taken",
        )

class LinkLimitExceededError(AppException):
    def __init__(self, scope: str = "account"):
        from app.core.config import settings
        if scope == "project":
            detail = f"Project link limit reached. Maximum {settings.MAX_LINKS_PER_PROJECT} links per project."
        else:
            detail = f"Account link limit reached. Maximum {settings.MAX_LINKS_PER_USER} links per account."
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
        )

class ForbiddenError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )


# ── Platform Admin ────────────────────────────────────────────────────────────

class PlatformAdminRequiredError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin access required",
        )

class SelfDeactivationError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot deactivate your own admin account",
        )


# ── Rate Limiting ─────────────────────────────────────────────────────────────

class RateLimitError(AppException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again.",
            headers={"Retry-After": "60"},
        )
