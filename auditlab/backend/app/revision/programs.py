"""Programmes de travail types par cycle (REV-16).

La bibliothèque est livrée par la migration 0042 (data/programmes.json) puis adaptée par le
cabinet. Un référentiel sans programme propre utilise celui de SYSCOHADA.
"""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.revision import ProgramStep
from app.revision.cycles import DEFAULT_FRAMEWORK


def seed(db: Session) -> None:
    """Installe la bibliothèque livrée (tests ; en exploitation, migration 0042)."""
    doc = json.loads((Path(__file__).parent / "data" / "programmes.json").read_text("utf-8"))
    for referentiel, cycles in doc.items():
        if referentiel == "source":
            continue
        for cycle, items in cycles.items():
            for i, (assertion, type_test, description) in enumerate(items, start=1):
                db.add(
                    ProgramStep(
                        referentiel=referentiel,
                        cycle=cycle,
                        assertion=assertion,
                        type_test=type_test,
                        description=description,
                        ordre=i,
                    )
                )


def referentiel_for(db: Session, code: str) -> str:
    exists = db.scalar(
        select(ProgramStep.id)
        .where(ProgramStep.referentiel == code, ProgramStep.deleted_at.is_(None))
        .limit(1)
    )
    return code if exists is not None else DEFAULT_FRAMEWORK


def steps(
    db: Session,
    code: str,
    cycle: str | None = None,
    assertion: str | None = None,
    active_only: bool = True,
) -> list[ProgramStep]:
    query = select(ProgramStep).where(
        ProgramStep.referentiel == referentiel_for(db, code), ProgramStep.deleted_at.is_(None)
    )
    if cycle:
        query = query.where(ProgramStep.cycle == cycle)
    if assertion:
        query = query.where(ProgramStep.assertion == assertion)
    if active_only:
        query = query.where(ProgramStep.actif.is_(True))
    return list(db.scalars(query.order_by(ProgramStep.cycle, ProgramStep.ordre)))
