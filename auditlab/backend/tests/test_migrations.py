"""Les migrations se rejouent dans les deux sens et installent les données de départ."""

from alembic import command
from sqlalchemy import text

from app.db import engine
from tests.conftest import alembic_config

SEEDED = ("risk_criteria", "risks", "controls", "risk_controls", "procedures", "tickmarks")


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
    }
