"""Persistence models for server-side authentication and security telemetry."""
from datetime import datetime
from uuid import UUID as PythonUUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, LargeBinary, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("token_hmac", name="uq_user_sessions_token_hmac"),
        Index("ix_user_sessions_user_id_active", "user_id", "revoked_at"),
        CheckConstraint("idle_expires_at <= absolute_expires_at", name="ck_user_sessions_expiry_order"),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[PythonUUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_user_sessions_user_id_users", ondelete="CASCADE"),
        nullable=False,
    )
    token_hmac: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    csrf_secret: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    client_ip_hmac: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)
    user_agent_hmac: Mapped[bytes | None] = mapped_column(LargeBinary(32), nullable=True)


class AuthRateLimit(Base, TimestampMixin):
    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        UniqueConstraint("purpose", "bucket_hmac", name="uq_auth_rate_limits_purpose_bucket"),
        Index("ix_auth_rate_limits_purpose_window", "purpose", "window_started_at"),
        CheckConstraint("attempt_count >= 0", name="ck_auth_rate_limits_attempt_count"),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    bucket_hmac: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InitialOwnerBootstrap(Base):
    """Single-use setup capability for the first personal workspace owner."""

    __tablename__ = "initial_owner_bootstrap"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_initial_owner_bootstrap_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    code_hmac: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SecurityAuditEvent(Base):
    __tablename__ = "security_audit_events"
    __table_args__ = (
        Index("ix_security_audit_events_actor_created", "actor_user_id", "created_at"),
        Index("ix_security_audit_events_workspace_created", "workspace_id", "created_at"),
    )

    id: Mapped[PythonUUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    actor_user_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_security_audit_events_actor_user_id_users", ondelete="SET NULL"),
        nullable=True,
    )
    workspace_id: Mapped[PythonUUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", name="fk_security_audit_events_workspace_id_workspaces", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
