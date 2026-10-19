"""Tableau des immobilisations d'un client (RCO-11) : acquisitions, cessions, amortissements
de l'exercice et écriture de dotation."""

import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.cabinet.dates import exercise_end
from app.cabinet.depreciation import Asset, schedule
from app.cabinet.entries import propose
from app.models.portfolio import Client, FixedAsset
from app.models.revision import AuditFile
from app.revision.balances import clean_account
from app.revision.controls import plan_roots
from app.revision.currency import decimals, quantum
from app.revision.mapping import assignments

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
ORIGIN = "RCO-11"


class AssetIn(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    libelle: str = Field(min_length=2, max_length=300)
    composant_de: uuid.UUID | None = None
    compte_immobilisation: str = Field(min_length=2, max_length=30)
    compte_amortissement: str = Field(min_length=2, max_length=30)
    compte_dotation: str = Field(min_length=2, max_length=30)
    date_mise_en_service: dt.date
    valeur_origine: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    mode: Literal["lineaire", "degressif"] = "lineaire"
    duree_annees: int = Field(ge=1, le=100)
    coefficient: Decimal | None = Field(default=None, gt=1, le=5)
    date_cession: dt.date | None = None
    prix_cession: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)

    @model_validator(mode="after")
    def _rules(self) -> "AssetIn":
        if self.mode == "degressif" and self.coefficient is None:
            raise ValueError("Coefficient dégressif obligatoire (valeur fiscale du pays)")
        if self.date_cession and self.date_cession < self.date_mise_en_service:
            raise ValueError("Cession antérieure à la mise en service")
        return self


def _assets(db: Session, client: Client) -> list[FixedAsset]:
    return list(
        db.scalars(
            select(FixedAsset)
            .where(FixedAsset.client_id == client.id, FixedAsset.deleted_at.is_(None))
            .order_by(FixedAsset.compte_immobilisation, FixedAsset.code)
        )
    )


def _calc(a: FixedAsset) -> Asset:
    return Asset(
        a.valeur_origine, a.date_mise_en_service, a.duree_annees, a.mode, a.coefficient,
        a.date_cession,
    )  # fmt: skip


def register(db: Session, file: AuditFile, client: Client) -> dict[str, Any]:
    q = quantum(decimals(db, file.devise))

    def ends(year: int) -> dt.date:
        return exercise_end(client, year)

    rows = []
    for a in _assets(db, client):
        if a.date_mise_en_service > file.date_fin or (
            a.date_cession and a.date_cession < file.date_debut
        ):
            continue  # pas encore en service, ou sortie avant l'exercice
        s = schedule(_calc(a), file.date_debut, file.date_fin, ends, q)
        sold = a.date_cession is not None and a.date_cession <= file.date_fin
        rows.append(
            {
                "id": str(a.id),
                "code": a.code,
                "libelle": a.libelle,
                "composant_de": str(a.composant_de) if a.composant_de else None,
                "compte_immobilisation": a.compte_immobilisation,
                "compte_amortissement": a.compte_amortissement,
                "compte_dotation": a.compte_dotation,
                "date_mise_en_service": a.date_mise_en_service.isoformat(),
                "mode": a.mode,
                "duree_annees": a.duree_annees,
                "coefficient": str(a.coefficient) if a.coefficient else None,
                "valeur_origine": str(a.valeur_origine),
                "acquisition": a.date_mise_en_service >= file.date_debut,
                "cession": sold,
                "date_cession": a.date_cession.isoformat() if a.date_cession else None,
                "prix_cession": str(a.prix_cession) if a.prix_cession is not None else None,
                "resultat_cession": str((a.prix_cession or ZERO) - s["vnc"]) if sold else None,
                **{k: str(v) for k, v in s.items()},
            }
        )
    # Rapprochement avec la balance N : valeurs brutes et amortissements des biens présents.
    books = {x.compte: x.soldes.get("N", ZERO) for x in assignments(db, file)}
    gross: dict[str, Decimal] = defaultdict(Decimal)
    amort: dict[str, Decimal] = defaultdict(Decimal)
    for r in rows:
        if not r["cession"]:
            gross[r["compte_immobilisation"]] += Decimal(r["valeur_origine"])
            amort[r["compte_amortissement"]] -= Decimal(r["cumul_fin"])
    checks = [
        {
            "compte": c,
            "tableau": str(v),
            "balance": str(books.get(c, ZERO)),
            "ecart": str(books.get(c, ZERO) - v),
        }  # fmt: skip
        for c, v in sorted({**gross, **amort}.items())
    ]
    total = {
        k: str(sum((Decimal(r[k]) for r in rows), ZERO))
        for k in ("valeur_origine", "dotation", "cumul_fin", "vnc")
    }
    return {"immobilisations": rows, "totaux": total, "rapprochement": checks}


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


def _apply(db: Session, file: AuditFile, client: Client, asset: FixedAsset, body: AssetIn) -> None:
    roots = plan_roots(db, file.framework_id)
    data = body.model_dump()
    for key in ("compte_immobilisation", "compte_amortissement", "compte_dotation"):
        data[key] = clean_account(data[key])
        if not any(data[key].startswith(r) for r in roots):
            raise HTTPException(422, f"Compte {data[key]} hors plan")
    if body.composant_de is not None:
        parent = db.get(FixedAsset, body.composant_de)
        if parent is None or parent.client_id != client.id or parent.id == asset.id:
            raise HTTPException(422, "Ensemble inconnu pour ce composant")
    for key, value in data.items():
        setattr(asset, key, value)


@router.get("/audit-files/{file_id}/fixed-assets")
def read_register(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, client = _context(db, file_id, user, False)
    return register(db, file, client)


@router.post("/audit-files/{file_id}/fixed-assets", status_code=status.HTTP_201_CREATED)
def add_asset(
    file_id: uuid.UUID, body: AssetIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    asset = FixedAsset(client_id=client.id)
    _apply(db, file, client, asset, body)
    db.add(asset)
    db.commit()
    return register(db, file, client)


@router.put("/audit-files/{file_id}/fixed-assets/{asset_id}")
def update_asset(
    file_id: uuid.UUID, asset_id: uuid.UUID, body: AssetIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    asset = db.get(FixedAsset, asset_id)
    if asset is None or asset.deleted_at is not None or asset.client_id != client.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Immobilisation introuvable")
    _apply(db, file, client, asset, body)
    db.commit()
    return register(db, file, client)


@router.delete("/audit-files/{file_id}/fixed-assets/{asset_id}", status_code=204)
def delete_asset(file_id: uuid.UUID, asset_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    _, client = _context(db, file_id, user, True)
    asset = db.get(FixedAsset, asset_id)
    if asset is None or asset.deleted_at is not None or asset.client_id != client.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Immobilisation introuvable")
    asset.deleted_at, asset.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/audit-files/{file_id}/fixed-assets/entry", status_code=status.HTTP_201_CREATED)
def depreciation_entry(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Écriture de dotation aux amortissements de l'exercice (débit dotation, crédit
    amortissement), proposée en écriture d'inventaire."""
    file, client = _context(db, file_id, user, True)
    rows = register(db, file, client)["immobilisations"]
    lines = []
    for r in rows:
        amount = Decimal(r["dotation"])
        if amount > 0:
            lines += [
                {
                    "compte": r["compte_dotation"],
                    "libelle": "Dotation aux amortissements",
                    "debit": amount,
                },
                {
                    "compte": r["compte_amortissement"],
                    "libelle": "Amortissements",
                    "credit": amount,
                },
            ]
    total = sum((Decimal(r["dotation"]) for r in rows), ZERO)
    return propose(
        db, file, user, ORIGIN, f"Dotations aux amortissements de l'exercice {file.exercice}",
        f"Tableau des immobilisations (RCO-11) : {len(rows)} immobilisation(s), dotation {total}.",
        lines,
    )  # fmt: skip
