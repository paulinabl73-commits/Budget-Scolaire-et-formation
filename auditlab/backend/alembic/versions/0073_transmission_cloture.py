"""transmission cloture (RCO-27)

Revision ID: 0073
Revises: 0072
Create Date: 2026-10-19 10:00:00
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '0073'
down_revision: str | None = '0072'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('audit_files', sa.Column('source_file_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_audit_files_source_file_id_audit_files'), 'audit_files', 'audit_files', ['source_file_id'], ['id'])
    op.add_column('closings', sa.Column('transmis_le', sa.DateTime(timezone=True), nullable=True))
    op.add_column('closings', sa.Column('transmis_par', sa.Uuid(), nullable=True))
    op.add_column('closings', sa.Column('transmis_a', sa.Uuid(), nullable=True))
    op.create_foreign_key(op.f('fk_closings_transmis_par_users'), 'closings', 'users', ['transmis_par'], ['id'])
    op.create_foreign_key(op.f('fk_closings_transmis_a_engagements'), 'closings', 'engagements', ['transmis_a'], ['id'])


def downgrade() -> None:
    op.drop_constraint(op.f('fk_closings_transmis_a_engagements'), 'closings', type_='foreignkey')
    op.drop_constraint(op.f('fk_closings_transmis_par_users'), 'closings', type_='foreignkey')
    op.drop_column('closings', 'transmis_a')
    op.drop_column('closings', 'transmis_par')
    op.drop_column('closings', 'transmis_le')
    op.drop_constraint(op.f('fk_audit_files_source_file_id_audit_files'), 'audit_files', type_='foreignkey')
    op.drop_column('audit_files', 'source_file_id')
