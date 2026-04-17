from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlatformUserResponse(BaseModel):
    id: str
    email: str
    is_active: bool
    is_verified: bool
    is_platform_admin: bool
    project_count: int
    link_count: int
    total_clicks: int
    created_at: datetime
    last_login_at: Optional[datetime]


class PlatformUserListResponse(BaseModel):
    users: list[PlatformUserResponse]
    next_cursor: Optional[str]   # ISO datetime string of last item's created_at
    total_count: int


class PlatformProjectResponse(BaseModel):
    id: str
    owner_user_id: Optional[str]
    owner_email: Optional[str] = None
    owner_org_id: Optional[str]
    name: str
    slug: str
    is_default: bool
    is_active: bool
    link_count: int
    created_at: datetime


class PlatformProjectListResponse(BaseModel):
    projects: list[PlatformProjectResponse]
    next_cursor: Optional[str]
    total_count: int


class PlatformLinkResponse(BaseModel):
    id: str
    project_id: str
    created_by: str
    created_by_email: Optional[str] = None
    short_code: str
    original_url: str
    title: Optional[str]
    is_active: bool
    click_count: int
    created_at: datetime


class PlatformLinkListResponse(BaseModel):
    links: list[PlatformLinkResponse]
    next_cursor: Optional[str]
    total_count: int


class ClicksPerDay(BaseModel):
    date: str
    clicks: int


class PlatformStatsResponse(BaseModel):
    total_users: int
    signups_today: int
    signups_this_week: int
    signups_this_month: int
    active_users_30d: int

    total_projects: int
    total_links: int
    total_clicks: int
    clicks_today: int
    clicks_this_week: int

    bot_percentage: float
    clicks_over_time: list[ClicksPerDay]   # last 30 days


class AuditLogResponse(BaseModel):
    id: str
    actor_id: Optional[str]
    actor_email: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    metadata: Optional[dict]
    ip_address: Optional[str]
    created_at: datetime


class AuditLogListResponse(BaseModel):
    logs: list[AuditLogResponse]
    next_cursor: Optional[str]


class AdminInviteRequest(BaseModel):
    email: str


class AdminAcceptRequest(BaseModel):
    token: str
