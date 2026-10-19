"""documents cloture (RCO-25)

Revision ID: 0072
Revises: 0071
Create Date: 2026-10-19 09:00:00
"""
import json
import uuid
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0072'
down_revision: str | None = '0071'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA = Path(__file__).resolve().parents[2] / "app" / "cabinet" / "data" / "documents_cloture.json"


def upgrade() -> None:
    op.add_column('closings', sa.Column('documents', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False))
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    table = sa.table("report_templates", sa.column("id"), sa.column("code"), sa.column("nom"),
                     sa.column("version"), sa.column("sections", postgresql.JSONB))
    op.bulk_insert(table, [{"id": uuid.uuid4(), "code": m["code"], "nom": m["nom"], "version": 1,
                            "sections": m["sections"]} for m in doc["modeles"]])


def downgrade() -> None:
    codes = [m["code"] for m in json.loads(DATA.read_text(encoding="utf-8"))["modeles"]]
    op.execute(sa.text("DELETE FROM report_templates WHERE code = ANY(:c)").bindparams(c=codes))
    op.drop_column('closings', 'documents')
