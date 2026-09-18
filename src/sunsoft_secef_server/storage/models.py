from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def utc_now() -> datetime:
    """Retourne l'heure UTC courante."""

    return datetime.now(
        timezone.utc
    )


class Base(DeclarativeBase):
    pass


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Tenant(Base):
    """
    Organisation cliente de la plateforme centrale.

    Un tenant représente l'espace de sécurité auquel
    appartiennent une ou plusieurs instances Odoo et
    leurs Agents SECeF autorisés.
    """

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    tenant_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    agents: Mapped[list["Agent"]] = relationship(
        back_populates="tenant",
    )

    odoo_credentials: Mapped[
        list["OdooCredential"]
    ] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    agent_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    environment: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    tenant: Mapped[
        Tenant | None
    ] = relationship(
        back_populates="agents",
    )

    credentials: Mapped[
        list["AgentCredential"]
    ] = relationship(
        back_populates="agent",
        cascade="all, delete-orphan",
    )

    jobs: Mapped[
        list["CentralJob"]
    ] = relationship(
        back_populates="agent",
    )


class OdooCredential(Base):
    """
    Identifiant d'accès utilisé par Odoo.

    Le token brut n'est jamais stocké.
    """

    __tablename__ = "odoo_credentials"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    credential_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    last_used_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    tenant: Mapped[Tenant] = relationship(
        back_populates="odoo_credentials",
    )


class AgentCredential(Base):
    """
    Identifiant d'accès propre à un Agent Windows.

    Plusieurs credentials peuvent exister pour
    permettre une rotation de clés sans interruption.
    """

    __tablename__ = "agent_credentials"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    credential_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    agent_id: Mapped[int] = mapped_column(
        ForeignKey(
            "agents.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    last_used_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    revoked_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    agent: Mapped[Agent] = relationship(
        back_populates="credentials",
    )


class CertificationRequest(Base):
    __tablename__ = "certification_requests"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    request_uid: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )

    agent_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )

    invoice_number: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    status: Mapped[JobStatus] = mapped_column(
        SqlEnum(
            JobStatus,
            native_enum=False,
            values_callable=lambda enum_class: [
                member.value
                for member in enum_class
            ],
        ),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    result: Mapped[
        dict | None
    ] = mapped_column(
        JSON,
        nullable=True,
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    jobs: Mapped[
        list["CentralJob"]
    ] = relationship(
        back_populates="certification_request",
    )


class CentralJob(Base):
    __tablename__ = "central_jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    job_uid: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
        index=True,
    )

    certification_request_id: Mapped[
        int
    ] = mapped_column(
        ForeignKey(
            "certification_requests.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    agent_id: Mapped[int] = mapped_column(
        ForeignKey(
            "agents.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    job_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[JobStatus] = mapped_column(
        SqlEnum(
            JobStatus,
            native_enum=False,
            values_callable=lambda enum_class: [
                member.value
                for member in enum_class
            ],
        ),
        nullable=False,
        default=JobStatus.PENDING,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )

    result: Mapped[
        dict | None
    ] = mapped_column(
        JSON,
        nullable=True,
    )

    error_message: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    delivered_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    certification_request: Mapped[
        CertificationRequest
    ] = relationship(
        back_populates="jobs",
    )

    agent: Mapped[Agent] = relationship(
        back_populates="jobs",
    )


Index(
    "ix_central_jobs_agent_status_created",
    CentralJob.agent_id,
    CentralJob.status,
    CentralJob.created_at,
)