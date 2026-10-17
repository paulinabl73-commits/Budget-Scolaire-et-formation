"""DAT-09 — analyses : opération et résultat de synthèse

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-17 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("operation", sa.String(length=40), nullable=True))
    op.add_column(
        "datasets",
        sa.Column(
            "resultat",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("datasets", "resultat")
    op.drop_column("datasets", "operation")
