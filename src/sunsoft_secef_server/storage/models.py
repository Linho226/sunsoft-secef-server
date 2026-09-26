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
    UniqueConstraint,
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

    sites: Mapped[list["Site"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    odoo_credentials: Mapped[
        list["OdooCredential"]
    ] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )


class Site(Base):
    """
    Site physique ou logique d'un Tenant.

    Un Tenant peut disposer de plusieurs Sites.
    Chaque Agent Windows peut ?tre rattach?
    ? un Site d?termin?.
    """

    __tablename__ = "sites"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "code",
            name="uq_sites_tenant_code",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tenants.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    site_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
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

    tenant: Mapped[Tenant] = relationship(
        back_populates="sites",
    )

    agents: Mapped[list["Agent"]] = relationship(
        back_populates="site",
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

    site_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "sites.id",
            name="fk_agents_site_id_sites",
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

    site: Mapped[
        Site | None
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


class AgentActivationCode(Base):
    """
    Code ? usage unique permettant de provisionner
    un Agent Windows pour un Tenant et un Site.

    Le code brut n'est jamais stock?.
    """

    __tablename__ = "agent_activation_codes"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    activation_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    tenant_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tenants.id",
            name=(
                "fk_agent_activation_codes_"
                "tenant_id_tenants"
            ),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    site_id: Mapped[int] = mapped_column(
        ForeignKey(
            "sites.id",
            name=(
                "fk_agent_activation_codes_"
                "site_id_sites"
            ),
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    code_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    used_by_agent_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "agents.id",
            name=(
                "fk_agent_activation_codes_"
                "used_by_agent_id_agents"
            ),
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
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


class AgentRelease(Base):
    """
    Version distribuable de l'Agent Windows Sunsoft SECeF.

    Le binaire reste sur le syst?me de fichiers.
    La base conserve uniquement ses m?tadonn?es.
    """

    __tablename__ = "agent_releases"

    __table_args__ = (
        UniqueConstraint(
            "version",
            name="uq_agent_releases_version",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    release_uid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        index=True,
    )

    version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    storage_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        unique=True,
    )

    sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )

    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    release_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )

    published_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    archived_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
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
