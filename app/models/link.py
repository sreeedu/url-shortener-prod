import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class Link(Base):
    __tablename__ = "links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Which project this link belongs to
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Who created this specific link.
    # Separate from project ownership — matters in Phase 3 when collaborators
    # can create links inside someone else's project.
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )

    original_url: Mapped[str] = mapped_column(Text, nullable=False)
    short_code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    project: Mapped["Project"] = relationship("Project", back_populates="links")
    clicks: Mapped[list["LinkClick"]] = relationship(
        "LinkClick", back_populates="link", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_links_project_id", "project_id"),
        Index("idx_links_created_by", "created_by"),
        # Primary analytics lookup — link + time range
        # Defined here rather than on LinkClick for co-location clarity
    )


class LinkClick(Base):
    __tablename__ = "link_clicks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    link_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("links.id", ondelete="CASCADE"),
        nullable=False,
    )
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Parsed at write time — analytics queries are simple GROUP BY,
    # never runtime string parsing. See core/useragent.py.
    device_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)

    link: Mapped["Link"] = relationship("Link", back_populates="clicks")

    __table_args__ = (
        Index("idx_link_clicks_link_id_clicked_at", "link_id", "clicked_at"),
        Index("idx_link_clicks_link_id_device", "link_id", "device_type"),
        Index("idx_link_clicks_link_id_browser", "link_id", "browser"),
    )
