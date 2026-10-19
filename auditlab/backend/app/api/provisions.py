"""Provisions et dépréciations d'une clôture (RCO-14) : créances douteuses selon la balance
âgée et la grille du dossier (calcul du REV-18), litiges et risques ; dotations et reprises
portant chaque compte au montant requis."""

import datetime as dt
import json
import uuid
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.api.third_parties import receivables_aging
from app.cabinet.entries import propose
from app.config import get_settings
from app.models.portfolio import Client, Provision
from app.models.revision import AccountingFramework, AuditFile
from app.revision.balances import clean_account
from app.revision.controls import plan_roots
from app.revision.mapping import assignments

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
ORIGIN = "RCO-14"


class ProvisionIn(BaseModel):
    nature: Literal["litige", "risque", "autre"]
    libelle: str = Field(min_length=2, max_length=300)
    montant_requis: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    compte_provision: str | None = Field(default=None, max_length=30)
    compte_dotation: str | None = Field(default=None, max_length=30)
    compte_reprise: str | None = Field(default=None, max_length=30)
    commentaire: str | None = Field(default=None, max_length=2000)


@lru_cache
def defaults() -> dict[str, dict[str, dict[str, str]]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "provisions.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}


def build(db: Session, file: AuditFile, user: Any) -> dict[str, Any]:
    try:
        aging = receivables_aging(file.id, user, db)
        receivables = {
            k: aging[k] for k in ("depreciation_requise", "depreciation_comptabilisee", "ecart")
        }
    except HTTPException:
        receivables = None  # pas de grand livre : créances non évaluées
    rows = list(
        db.scalars(
            select(Provision)
            .where(Provision.audit_file_id == file.id, Provision.deleted_at.is_(None))
            .order_by(Provision.nature, Provision.libelle)
        )
    )
    books = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file)}
    required: dict[str, Decimal] = defaultdict(Decimal)
    for p in rows:
        required[p.compte_provision] += p.montant_requis
    accounts = [
        {
            "compte": compte,
            "requis": str(amount),
            "comptabilise": str(-sum((v for c, v in books.items() if c.startswith(compte)), ZERO)),
        }
        for compte, amount in sorted(required.items())
    ]
    for a in accounts:
        a["ecart"] = str(Decimal(a["requis"]) - Decimal(a["comptabilise"]))
    code = db.get(AccountingFramework, file.framework_id).code
    return {
        "creances": receivables,
        "provisions": [
            {
                "id": str(p.id),
                "nature": p.nature,
                "libelle": p.libelle,
                "montant_requis": str(p.montant_requis),
                "compte_provision": p.compte_provision,
                "compte_dotation": p.compte_dotation,
                "compte_reprise": p.compte_reprise,
                "commentaire": p.commentaire,
            }
            for p in rows
        ],
        "comptes": accounts,
        "comptes_proposes": defaults().get(code, {}),
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


@router.get("/audit-files/{file_id}/provisions")
def read_provisions(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, False)
    return build(db, file, user)


@router.post("/audit-files/{file_id}/provisions", status_code=status.HTTP_201_CREATED)
def add_provision(
    file_id: uuid.UUID, body: ProvisionIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    code = db.get(AccountingFramework, file.framework_id).code
    proposed = defaults().get(code, {}).get(body.nature, {})
    roots = plan_roots(db, file.framework_id)
    values = {}
    for key in ("provision", "dotation", "reprise"):
        compte = clean_account(getattr(body, f"compte_{key}") or proposed.get(key, ""))
        if not compte or not any(compte.startswith(r) for r in roots):
            raise HTTPException(422, f"Compte de {key} {compte or '(vide)'} hors plan")
        values[f"compte_{key}"] = compte
    db.add(
        Provision(
            client_id=client.id,
            audit_file_id=file.id,
            nature=body.nature,
            libelle=body.libelle,
            montant_requis=body.montant_requis,
            commentaire=body.commentaire,
            **values,
        )
    )
    db.commit()
    return build(db, file, user)


@router.delete("/audit-files/{file_id}/provisions/{provision_id}", status_code=204)
def delete_provision(
    file_id: uuid.UUID, provision_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    file, _ = _context(db, file_id, user, True)
    row = db.get(Provision, provision_id)
    if row is None or row.deleted_at is not None or row.audit_file_id != file.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Provision introuvable")
    row.deleted_at, row.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/audit-files/{file_id}/provisions/entry", status_code=status.HTTP_201_CREATED)
def provision_entry(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = _context(db, file_id, user, True)
    data = build(db, file, user)
    s = get_settings()
    lines = []

    def move(gap: Decimal, provision: str, dotation: str, reprise: str, label: str) -> None:
        if gap > 0:
            lines.extend(
                [
                    {"compte": dotation, "libelle": f"Dotation : {label}", "debit": gap},
                    {"compte": provision, "libelle": label, "credit": gap},
                ]
            )
        elif gap < 0:
            lines.extend(
                [
                    {"compte": provision, "libelle": label, "debit": -gap},
                    {"compte": reprise, "libelle": f"Reprise : {label}", "credit": -gap},
                ]
            )

    if data["creances"]:
        move(
            Decimal(data["creances"]["ecart"]),
            s.compte_depreciation_clients,
            s.compte_dotation_creances,
            s.compte_reprise_creances,
            "Dépréciation des créances clients",
        )
    by_account = {p["compte_provision"]: p for p in data["provisions"]}
    for a in data["comptes"]:
        p = by_account[a["compte"]]
        move(
            Decimal(a["ecart"]),
            a["compte"],
            p["compte_dotation"],
            p["compte_reprise"],
            f"Provision {a['compte']}",
        )
    return propose(
        db,
        file,
        user,
        ORIGIN,
        f"Provisions et dépréciations de l'exercice {file.exercice}",
        "Créances douteuses selon la balance âgée et la grille du dossier ; litiges et risques "
        f"(RCO-14) : {len(data['provisions'])} provision(s).",
        lines,
    )
