"""Affectation des comptes aux postes (REV-08, REV-09), comptes non affectés et aperçu des
états, refusé tant que la liste n'est pas vide (REV-10)."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.audit_files import ON_CREATE, get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.models.revision import AccountingFramework, AccountMapping, AuditFile, StatementLine
from app.revision.balances import clean_account
from app.revision.mapping import (
    PERIODS,
    UnmappedError,
    assignments,
    file_values,
    overrides,
    postes,
    unmapped,
)

router = APIRouter(tags=["Révision – affectation"])


class MappingIn(BaseModel):
    poste: str = Field(min_length=1, max_length=20)
    poste_crediteur: str | None = Field(default=None, max_length=20)
    commentaire: str | None = Field(default=None, max_length=2000)


def _assignable(line: StatementLine) -> bool:
    """Poste de détail (pas un total calculé) : il peut recevoir des comptes."""
    return bool(line.racines) or not line.formule


def _account_out(a: Any, labels: dict[str, str]) -> dict[str, Any]:
    return {
        "compte": a.compte,
        "libelle": a.libelle,
        "soldes": {p: str(v) for p, v in a.soldes.items()},
        "postes": a.postes,
        "libelles_postes": {p: labels.get(c) if c else None for p, c in a.postes.items()},
        "racines": a.racines,
        "origine": a.origine,
        "poste_manuel": a.mapping.poste if a.mapping else None,
        "poste_crediteur": a.mapping.poste_crediteur if a.mapping else None,
        "commentaire": a.mapping.commentaire if a.mapping else None,
        "affecte": all(p is not None for p in a.postes.values()),
    }


@router.get("/audit-files/{file_id}/mapping")
def read_mapping(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    lines = postes(db, file.framework_id)
    labels = {ln.code: ln.libelle for ln in lines}
    items = assignments(db, file)
    return {
        "comptes": [_account_out(a, labels) for a in items],
        "non_affectes": [a.compte for a in unmapped(items)],
        "postes": [
            {"code": ln.code, "libelle": ln.libelle, "etat": ln.etat, "nature": ln.nature}
            for ln in lines
            if _assignable(ln)
        ],
    }


@router.put("/audit-files/{file_id}/mapping/{compte}")
def set_mapping(
    file_id: uuid.UUID, compte: str, body: MappingIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    compte = clean_account(compte)
    codes = {ln.code for ln in postes(db, file.framework_id) if _assignable(ln)}
    for code in (body.poste, body.poste_crediteur):
        if code is not None and code not in codes:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"Poste {code} inconnu ou non affectable"
            )
    mapping = overrides(db, file.id).get(compte)
    if mapping is None:
        mapping = AccountMapping(engagement_id=file.engagement_id, audit_file_id=file.id,
                                 compte=compte, poste=body.poste)  # fmt: skip
        db.add(mapping)
    mapping.poste = body.poste
    mapping.poste_crediteur = body.poste_crediteur
    mapping.commentaire = body.commentaire
    db.commit()
    return read_mapping(file_id, user, db)


@router.delete("/audit-files/{file_id}/mapping/{compte}")
def reset_mapping(
    file_id: uuid.UUID, compte: str, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Retour à l'affectation automatique."""
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    mapping = overrides(db, file.id).get(clean_account(compte))
    if mapping is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aucune affectation manuelle")
    mapping.deleted_at, mapping.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()
    return read_mapping(file_id, user, db)


def values_or_409(db: Session, file: AuditFile) -> dict[str, dict[str, Decimal]]:
    try:
        return file_values(db, file)
    except UnmappedError as exc:
        if not exc.comptes:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
        detail = {"message": str(exc), "comptes": exc.comptes}
        raise HTTPException(status.HTTP_409_CONFLICT, detail) from exc


@router.get("/audit-files/{file_id}/statements/preview")
def preview(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Aperçu des états N et N-1 ; refusé tant qu'un compte n'est pas affecté (REV-10)."""
    file, _ = get_file(db, file_id, user)
    values = values_or_409(db, file)
    lines = postes(db, file.framework_id)
    states: dict[str, list[dict[str, Any]]] = {}
    for ln in lines:
        states.setdefault(ln.etat, []).append({
            "code": ln.code, "libelle": ln.libelle, "niveau": ln.niveau,
            "total": not _assignable(ln),
            **{p: str(values[p].get(ln.code, Decimal(0))) for p in PERIODS},
        })  # fmt: skip
    checks = []
    for rule in db.get(AccountingFramework, file.framework_id).regles:
        gaps = {p: values[p].get(rule["gauche"], Decimal(0)) - values[p].get(rule["droite"],
                Decimal(0)) for p in PERIODS}  # fmt: skip
        checks.append({"code": rule["code"], "libelle": rule["libelle"],
                       "ecarts": {p: str(v) for p, v in gaps.items()},
                       "ok": all(v == 0 for v in gaps.values())})  # fmt: skip
    return {"etats": states, "controles": checks}


def carry_over_mappings(db: Session, file: AuditFile, previous: AuditFile) -> None:
    """REV-04 : les affectations manuelles du dossier N-1 sont reprises."""
    for m in overrides(db, previous.id).values():
        db.add(AccountMapping(
            engagement_id=file.engagement_id, audit_file_id=file.id, compte=m.compte,
            poste=m.poste, poste_crediteur=m.poste_crediteur, commentaire=m.commentaire,
        ))  # fmt: skip


ON_CREATE.append(carry_over_mappings)
