"""agent releases

Revision ID: 0004_agent_releases
Revises: 0003_activation_codes
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_agent_releases"
down_revision: Union[
    str,
    Sequence[str],
    None,
] = "0003_activation_codes"

branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_releases",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "release_uid",
            sa.String(length=36),
            nullable=False,
        ),

        sa.Column(
            "version",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "filename",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "storage_path",
            sa.String(length=500),
            nullable=False,
        ),

        sa.Column(
            "sha256",
            sa.String(length=64),
            nullable=False,
        ),

        sa.Column(
            "file_size",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "release_notes",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "is_published",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "archived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.UniqueConstraint(
            "release_uid",
        ),

        sa.UniqueConstraint(
            "version",
            name="uq_agent_releases_version",
        ),

        sa.UniqueConstraint(
            "storage_path",
        ),
    )

    op.create_index(
        op.f(
            "ix_agent_releases_release_uid"
        ),
        "agent_releases",
        ["release_uid"],
        unique=True,
    )

    op.create_index(
        op.f(
            "ix_agent_releases_version"
        ),
        "agent_releases",
        ["version"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_agent_releases_sha256"
        ),
        "agent_releases",
        ["sha256"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_agent_releases_is_published"
        ),
        "agent_releases",
        ["is_published"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_agent_releases_published_at"
        ),
        "agent_releases",
        ["published_at"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_agent_releases_archived_at"
        ),
        "agent_releases",
        ["archived_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f(
            "ix_agent_releases_archived_at"
        ),
        table_name="agent_releases",
    )

    op.drop_index(
        op.f(
            "ix_agent_releases_published_at"
        ),
        table_name="agent_releases",
    )

    op.drop_index(
        op.f(
            "ix_agent_releases_is_published"
        ),
        table_name="agent_releases",
    )

    op.drop_index(
        op.f(
            "ix_agent_releases_sha256"
        ),
        table_name="agent_releases",
    )

    op.drop_index(
        op.f(
            "ix_agent_releases_version"
        ),
        table_name="agent_releases",
    )

    op.drop_index(
        op.f(
            "ix_agent_releases_release_uid"
        ),
        table_name="agent_releases",
    )

    op.drop_table(
        "agent_releases"
    )
