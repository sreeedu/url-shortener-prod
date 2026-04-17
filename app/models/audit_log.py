import uuid
from datetime import datetime
from typing import Any
from sqlalchemy import String, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # actor_id goes NULL if user is deleted (SET NULL).
    # actor_email is captured at write time and never changes —
    # preserves identity in the audit trail even after user deletion.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Dot-namespaced action string e.g. "project.created", "platform.user_deactivated"
    action: Mapped[str] = mapped_column(String(100), nullable=False)

    # What was acted on
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Action-specific context — old values, new values, reasons, etc.
    # DB column is "meta". Python attribute is "meta_data" because SQLAlchemy
    # reserves "metadata" as a class-level attribute on all declarative models.
    meta_data: Mapped[dict[str, Any] | None] = mapped_column("meta", JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor: Mapped["User | None"] = relationship(
        "User",
        back_populates="audit_logs",
        foreign_keys=[actor_id],
    )

    __table_args__ = (
        # All indexes are composite ending in created_at DESC so ORDER BY is index-backed
        Index("idx_audit_actor_created_at", "actor_id", text("created_at DESC")),
        Index(
            "idx_audit_target_created_at",
            "target_type", "target_id", text("created_at DESC"),
        ),
        Index("idx_audit_action_created_at", "action", text("created_at DESC")),
        Index("idx_audit_created_at", text("created_at DESC")),
    )
