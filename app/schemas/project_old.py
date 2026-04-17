from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re

HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _slugify_for_check(name: str) -> str:
    """Reproduce the slugification logic so we can check the resulting slug."""
    import re as _re
    slug = name.lower().strip()
    slug = _re.sub(r"[^\w\s-]", "", slug)
    slug = _re.sub(r"[\s_]+", "-", slug)
    slug = _re.sub(r"-+", "-", slug)
    return slug.strip("-")[:100] or "project"


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = Field(None)

    @field_validator("name")
    @classmethod
    def validate_name_slug(cls, v: str) -> str:
        from app.core.reserved_codes import is_reserved
        slug = _slugify_for_check(v)
        if is_reserved(slug):
            raise ValueError(
                f"'{v}' produces a reserved or disallowed slug. Please choose a different project name."
            )
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not HEX_COLOR_RE.match(v):
            raise ValueError("Color must be a valid hex code e.g. '#4F46E5'")
        return v


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    color: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        from app.core.reserved_codes import is_reserved
        slug = _slugify_for_check(v)
        if is_reserved(slug):
            raise ValueError(
                f"'{v}' produces a reserved or disallowed slug. Please choose a different project name."
            )
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not HEX_COLOR_RE.match(v):
            raise ValueError("Color must be a valid hex code e.g. '#4F46E5'")
        return v


class ProjectResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    color: Optional[str]
    is_default: bool
    is_active: bool
    link_count: int
    total_clicks: int
    clicks_this_month: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class ProjectListResponse(BaseModel):
    projects: list[ProjectResponse]
    total: int
    page: int
    per_page: int


# ── Project Analytics ─────────────────────────────────────────────────────────

class TopLink(BaseModel):
    link_id: str
    short_code: str
    title: Optional[str]
    clicks: int


class ClicksOverTime(BaseModel):
    date: str
    clicks: int


class ProjectAnalyticsResponse(BaseModel):
    project_id: str
    project_name: str

    total_links: int
    active_links: int
    total_clicks: int
    unique_visitors: int
    clicks_today: int
    clicks_this_week: int
    clicks_this_month: int

    top_links: list[TopLink]
    devices: dict[str, int]
    browsers: dict[str, int]
    os_breakdown: dict[str, int]
    referers: dict[str, int]
    clicks_over_time: list[ClicksOverTime]
    peak_hour: Optional[int]
    bot_clicks: int
    human_clicks: int
