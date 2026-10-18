"""Référentiel de restitution IFRS : table de passage depuis le SYSCOHADA révisé (IFR-01, IFR-03).

Revision ID: 0050
Revises: 0049
"""

import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

DATA = Path(__file__).resolve().parents[2] / "app" / "revision" / "data" / "ifrs_2024.json"


def upgrade() -> None:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    jsonb = postgresql.JSONB
    fw = sa.table("accounting_frameworks", *(sa.column(c) for c in (
        "id", "code", "version", "libelle", "pays", "date_effet", "actif", "source")),
        *(sa.column(c, jsonb) for c in ("ratios", "bases_seuil", "regles", "branches")))  # fmt: skip
    lines = sa.table("statement_lines", *(sa.column(c) for c in (
        "id", "framework_id", "etat", "code", "libelle", "nature", "formule", "ordre", "niveau")),
        sa.column("racines", jsonb))  # fmt: skip
    fid = uuid.uuid4()
    op.execute(fw.insert().values(
        id=fid, code=doc["code"], version=doc["version"], libelle=doc["libelle"], pays=doc["pays"],
        date_effet=sa.cast(doc["date_effet"], sa.Date), actif=True, source=doc["source"],
        ratios=doc["ratios"], bases_seuil=doc["bases_seuil"], regles=doc["regles"], branches=[]))  # fmt: skip
    for p in doc["postes"]:
        op.execute(lines.insert().values(
            id=uuid.uuid4(), framework_id=fid, etat=p["etat"], code=p["code"], libelle=p["libelle"],
            nature=p["nature"], racines=p["racines"], formule=p["formule"], ordre=p["ordre"],
            niveau=p["niveau"]))  # fmt: skip


def downgrade() -> None:
    conn = op.get_bind()
    ids = [r[0] for r in conn.execute(sa.text(
        "SELECT id FROM accounting_frameworks WHERE code = 'IFRS' AND version = '2024'"))]  # fmt: skip
    for fid in ids:
        conn.execute(sa.text("DELETE FROM statement_lines WHERE framework_id = :f"), {"f": fid})
        conn.execute(sa.text("DELETE FROM accounting_frameworks WHERE id = :f"), {"f": fid})
