import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Boolean, DateTime, ForeignKey,
    Index, CheckConstraint, func, text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Exactly one of owner_user_id / owner_org_id must be set.
    # Enforced by DB check constraint ck_projects_exactly_one_owner.
    # owner_org_id has no FK yet — Phase 3 adds it when organisations table exists.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    owner_org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Hex color for frontend project cards e.g. "#4F46E5"
    # DB check constraint ensures format correctness
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)

    # True only for the auto-created Personal project.
    # DB partial unique index ensures only one default per owner.
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, onupdate=func.now()
    )

    # Relationships
    owner_user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="projects",
        foreign_keys=[owner_user_id],
    )
    links: Mapped[list["Link"]] = relationship(
        "Link", back_populates="project", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Exactly one owner must be set — never both, never neither
        CheckConstraint(
            "(owner_user_id IS NOT NULL)::int + (owner_org_id IS NOT NULL)::int = 1",
            name="ck_projects_exactly_one_owner",
        ),
        # Color must be valid hex format if provided
        CheckConstraint(
            "color IS NULL OR color ~ '^#[0-9a-fA-F]{6}$'",
            name="ck_projects_color_hex",
        ),
        # Basic indexes
        Index("idx_projects_owner_user_id", "owner_user_id"),
        Index("idx_projects_owner_org_id", "owner_org_id"),
        # Unique slug per user-owned project
        Index(
            "uq_projects_owner_user_slug",
            "owner_user_id", "slug",
            unique=True,
            postgresql_where=text("owner_user_id IS NOT NULL"),
        ),
        # Unique slug per org-owned project
        Index(
            "uq_projects_owner_org_slug",
            "owner_org_id", "slug",
            unique=True,
            postgresql_where=text("owner_org_id IS NOT NULL"),
        ),
        # Only one default project per user
        Index(
            "uq_projects_one_default_per_user",
            "owner_user_id",
            unique=True,
            postgresql_where=text("is_default = true AND owner_user_id IS NOT NULL"),
        ),
        # Only one default project per org
        Index(
            "uq_projects_one_default_per_org",
            "owner_org_id",
            unique=True,
            postgresql_where=text("is_default = true AND owner_org_id IS NOT NULL"),
        ),
    )
