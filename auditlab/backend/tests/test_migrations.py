"""Les migrations se rejouent dans les deux sens et installent les données de départ."""

from alembic import command
from sqlalchemy import text

from app.db import engine
from tests.conftest import alembic_config

SEEDED = (
    "risk_criteria", "risks", "controls", "risk_controls", "procedures", "tickmarks",
    "accounting_frameworks", "framework_accounts", "statement_lines", "normative_frameworks",
    "currencies",
)  # fmt: skip


def test_migrations_aller_retour_et_donnees_de_depart():
    cfg = alembic_config()
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    with engine.connect() as conn:
        counts = {
            t: conn.scalar(text(f"SELECT count(*) FROM {t}"))  # noqa: S608
            for t in SEEDED
        }
    assert counts == {
        "risk_criteria": 5,
        "risks": 11,
        "controls": 15,
        "risk_controls": 15,
        "procedures": 16,
        "tickmarks": 6,
        "accounting_frameworks": 2,  # SYSCOHADA révisé et modèle CIPRES
        "framework_accounts": 168,
        "statement_lines": 120,
        "normative_frameworks": 3,
        "currencies": 6,
    }
    # Les valeurs JSONB des référentiels sont des tableaux, pas des chaînes ré-encodées.
    with engine.connect() as conn:
        kinds = conn.execute(
            text(
                "SELECT DISTINCT jsonb_typeof(ratios), jsonb_typeof(regles), "
                "jsonb_typeof(bases_seuil), jsonb_typeof(branches) FROM accounting_frameworks"
            )
        ).all()
        racines = conn.scalar(text("SELECT DISTINCT jsonb_typeof(racines) FROM statement_lines"))
    assert kinds == [("array", "array", "array", "array")]
    assert racines == "array"
