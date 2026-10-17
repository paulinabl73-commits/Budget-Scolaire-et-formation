"""Tableau des flux de trésorerie et règle de concordance de la trésorerie (REV-24) ajoutés
au référentiel SYSCOHADA 2017 déjà installé.

Revision ID: 0041
Revises: 0040
"""

import json
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None

DATA = Path(__file__).resolve().parents[2] / "app" / "revision" / "data" / "syscohada_2017.json"


def upgrade() -> None:
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    conn = op.get_bind()
    fw = conn.execute(
        sa.text("SELECT id, regles FROM accounting_frameworks WHERE code = 'SYSCOHADA' AND version = '2017'")
    ).first()
    if fw is None:
        return
    existing = {r[0] for r in conn.execute(
        sa.text("SELECT code FROM statement_lines WHERE framework_id = :f"), {"f": fw.id})}  # fmt: skip
    lines = sa.table("statement_lines", *(sa.column(c) for c in (
        "id", "framework_id", "etat", "code", "libelle", "nature", "formule", "ordre", "niveau")),
        sa.column("racines", postgresql.JSONB))  # fmt: skip
    for p in doc["postes"]:
        if p["etat"] == "flux_tresorerie" and p["code"] not in existing:
            op.execute(lines.insert().values(
                id=uuid.uuid4(), framework_id=fw.id, etat=p["etat"], code=p["code"],
                libelle=p["libelle"], nature=p["nature"], racines=p["racines"],
                formule=p["formule"], ordre=p["ordre"], niveau=p["niveau"]))  # fmt: skip
    codes = {r["code"] for r in fw.regles}
    added = [r for r in doc["regles"] if r["code"] not in codes]
    if added:
        table = sa.table("accounting_frameworks", sa.column("id"),
                         sa.column("regles", postgresql.JSONB))  # fmt: skip
        op.execute(table.update().where(table.c.id == fw.id).values(regles=fw.regles + added))


def downgrade() -> None:
    conn = op.get_bind()
    fw = conn.execute(
        sa.text("SELECT id, regles FROM accounting_frameworks WHERE code = 'SYSCOHADA' AND version = '2017'")
    ).first()
    if fw is None:
        return
    conn.execute(sa.text("DELETE FROM statement_lines WHERE framework_id = :f AND etat = 'flux_tresorerie'"),
                 {"f": fw.id})  # fmt: skip
    table = sa.table("accounting_frameworks", sa.column("id"), sa.column("regles", postgresql.JSONB))
    kept = [r for r in fw.regles if r["code"] != "tresorerie_concordante"]
    op.execute(table.update().where(table.c.id == fw.id).values(regles=kept))
