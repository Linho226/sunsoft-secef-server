"""add agent mcf status

Revision ID: 0005_agent_mcf_status
Revises: 0004_agent_releases
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_agent_mcf_status"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "0004_agent_releases"

branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_mcf_status",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "agent_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "sent_transactions",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "available_transactions",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "last_connection_datetime",
            sa.String(length=14),
            nullable=False,
        ),

        sa.Column(
            "connection_age_seconds",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "connection_stale",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.id"],
            name=(
                "fk_agent_mcf_status_"
                "agent_id_agents"
            ),
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id"
        ),

        sa.UniqueConstraint(
            "agent_id",
            name=(
                "uq_agent_mcf_status_"
                "agent_id"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_table(
        "agent_mcf_status"
    )
