from pydantic import BaseModel, HttpUrl, field_validator, Field
from typing import Optional
from datetime import datetime
from enum import Enum
import ipaddress
import re
from urllib.parse import urlparse
from app.core.reserved_codes import is_reserved


class ExpiryOption(str, Enum):
    ONE_DAY = "1d"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    NINETY_DAYS = "90d"
    NEVER = "never"


EXPIRY_DAYS = {
    ExpiryOption.ONE_DAY: 1,
    ExpiryOption.SEVEN_DAYS: 7,
    ExpiryOption.THIRTY_DAYS: 30,
    ExpiryOption.NINETY_DAYS: 90,
    ExpiryOption.NEVER: None,
}

CUSTOM_CODE_PATTERN = re.compile(r"^[a-zA-Z0-9\-]+$")

# RESERVED_CODES = {
#     "api", "admin", "login", "signup", "dashboard",
#     "health", "docs", "redoc", "openapi", "static",
#     "favicon.ico", "robots.txt", "sitemap.xml",
#     "assets", "public", "uploads", "media", "images",
# }


def _is_private_url(url_str: str) -> bool:
    """Block SSRF targets — private IPs, loopback, link-local, localhost."""
    try:
        parsed = urlparse(url_str)
        hostname = parsed.hostname or ""

        if not hostname:
            return True

        blocked_hostnames = {"localhost", "localtest.me"}
        if hostname.lower() in blocked_hostnames:
            return True

        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        except ValueError:
            pass

        return False
    except Exception:
        return True


class CreateLinkRequest(BaseModel):
    original_url: HttpUrl
    expiry: ExpiryOption = ExpiryOption.NEVER
    custom_code: Optional[str] = Field(None, min_length=4, max_length=20)
    title: Optional[str] = Field(None, max_length=255)

    @field_validator("original_url", mode="before")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = str(v).strip()
        if len(v) > 2048:
            raise ValueError("URL must be 2048 characters or less")
        if _is_private_url(v):
            raise ValueError("URL points to a private or reserved address")
        return v

    @field_validator("custom_code")
    @classmethod
    def validate_custom_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not CUSTOM_CODE_PATTERN.match(v):
            raise ValueError("Custom code can only contain letters, numbers, and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Custom code cannot start or end with a hyphen")
        if is_reserved(v.lower()):
            raise ValueError(f"'{v}' is a reserved word and cannot be used")
        return v


class UpdateLinkRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=255)
    is_active: Optional[bool] = None


class LinkResponse(BaseModel):
    id: str
    project_id: str
    short_code: str
    short_url: str
    original_url: str
    title: Optional[str]
    expires_at: Optional[datetime]
    is_active: bool
    click_count: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class LinkListResponse(BaseModel):
    links: list[LinkResponse]
    total: int
    page: int
    per_page: int


# ── Link Analytics ────────────────────────────────────────────────────────────

class ClicksOverTime(BaseModel):
    date: str
    clicks: int


class LinkAnalyticsResponse(BaseModel):
    link_id: str
    short_code: str

    total_clicks: int
    unique_visitors: int
    clicks_today: int
    clicks_this_week: int
    clicks_this_month: int

    devices: dict[str, int]
    browsers: dict[str, int]
    os_breakdown: dict[str, int]
    referers: dict[str, int]
    clicks_over_time: list[ClicksOverTime]
    peak_hour: Optional[int]
    bot_clicks: int
    human_clicks: int
