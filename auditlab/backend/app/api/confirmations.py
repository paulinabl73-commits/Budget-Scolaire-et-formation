"""Circularisation (REV-19) : sélection des tiers, lettres PDF et Word, suivi des réponses et
rapprochement automatique des écarts."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.audit.listeners import record_event
from app.config import get_settings
from app.models.revision import AuditFile, Confirmation
from app.models.universe import AuditableEntity
from app.models.user import User
from app.revision import confirmations as letters
from app.revision.imports import active_balance
from app.revision.mapping import assignments
from app.revision.third_parties import Item, match

router = APIRouter(tags=["Révision – circularisation"])
ZERO = Decimal(0)
TYPES = "^(banque|client|fournisseur|avocat)$"
STATUTS = ("a_envoyer", "envoyee", "relancee", "recue", "sans_reponse")
ROOTS = {"client": ["41"], "fournisseur": ["40"]}
SIGN = {"client": 1, "fournisseur": -1, "banque": 1, "avocat": 1}
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class SelectIn(BaseModel):
    type: str = Field(pattern="^(banque|client|fournisseur)$")
    seuil: Decimal | None = Field(default=None, ge=0)
    maximum: int | None = Field(default=None, ge=1, le=500)


class ConfirmationIn(BaseModel):
    type: str = Field(pattern=TYPES)
    tiers: str = Field(min_length=1, max_length=200)
    compte: str | None = Field(default=None, max_length=30)
    adresse: str | None = Field(default=None, max_length=2000)
    email: str | None = Field(default=None, max_length=200)
    solde_comptable: Decimal | None = None


class ConfirmationUpdate(BaseModel):
    statut: str | None = Field(default=None, pattern="^(" + "|".join(STATUTS) + ")$")
    adresse: str | None = Field(default=None, max_length=2000)
    email: str | None = Field(default=None, max_length=200)
    envoyee_le: dt.date | None = None
    relancee_le: dt.date | None = None
    reponse_le: dt.date | None = None
    solde_confirme: Decimal | None = None
    reponse: str | None = Field(default=None, max_length=5000)
    explication: str | None = Field(default=None, max_length=5000)
    procedure_alternative: str | None = Field(default=None, max_length=5000)


def conf_out(c: Confirmation) -> dict[str, Any]:
    gap = None
    if c.solde_confirme is not None and c.solde_comptable is not None:
        gap = c.solde_comptable - c.solde_confirme
    return {
        "id": str(c.id),
        "numero": c.numero,
        "reference": f"CIRC-{c.numero:03d}",
        "type": c.type,
        "tiers": c.tiers,
        "compte": c.compte,
        "adresse": c.adresse,
        "email": c.email,
        "solde_comptable": str(c.solde_comptable) if c.solde_comptable is not None else None,
        "statut": c.statut,
        "envoyee_le": c.envoyee_le.isoformat() if c.envoyee_le else None,
        "relancee_le": c.relancee_le.isoformat() if c.relancee_le else None,
        "reponse_le": c.reponse_le.isoformat() if c.reponse_le else None,
        "solde_confirme": str(c.solde_confirme) if c.solde_confirme is not None else None,
        "ecart": str(gap) if gap is not None else None,
        "reponse": c.reponse,
        "explication": c.explication,
        "procedure_alternative": c.procedure_alternative,
    }


def _ledger_items(db: Session, file: AuditFile, roots: list[str]) -> list[Item] | None:
    import polars as pl

    from app.analytics.store import data_dir
    from app.models.data import Dataset

    gl = active_balance(db, file.id, "N", "grand_livre")
    if gl is None or gl.dataset_id is None:
        return None
    df = pl.read_parquet(data_dir() / db.get(Dataset, gl.dataset_id).chemin_parquet)
    return [i for s in match(df, roots).values() for i in s.ouvertes]


def candidates(db: Session, file: AuditFile, kind: str) -> list[dict[str, Any]]:
    """Tiers et soldes à circulariser, vus de l'entité (créance client, dette fournisseur)."""
    s = get_settings()
    if kind == "banque":
        return [
            {
                "tiers": a.libelle or f"Banque – compte {a.compte}",
                "compte": a.compte,
                "solde": a.soldes.get("N", ZERO),
            }
            for a in assignments(db, file)
            if any(a.compte.startswith(r) for r in s.racines_banques)
        ]
    items = _ledger_items(db, file, ROOTS[kind])
    if items and any(i.tiers for i in items):
        parties: dict[str, dict[str, Any]] = {}
        for i in items:
            key = i.tiers or i.compte
            p = parties.setdefault(key, {"tiers": key, "compte": i.compte, "solde": ZERO})
            p["solde"] += SIGN[kind] * i.net
        return list(parties.values())
    return [
        {
            "tiers": a.libelle or a.compte,
            "compte": a.compte,
            "solde": SIGN[kind] * a.soldes.get("N", ZERO),
        }
        for a in assignments(db, file)
        if any(a.compte.startswith(r) for r in ROOTS[kind])
    ]


def _next_number(db: Session, file_id: uuid.UUID) -> int:
    last = db.scalar(
        select(func.max(Confirmation.numero)).where(Confirmation.audit_file_id == file_id)
    )
    return (last or 0) + 1


def _file_confirmations(
    db: Session, file_id: uuid.UUID, kind: str | None = None
) -> list[Confirmation]:
    query = select(Confirmation).where(
        Confirmation.audit_file_id == file_id, Confirmation.deleted_at.is_(None)
    )
    if kind:
        query = query.where(Confirmation.type == kind)
    return list(db.scalars(query.order_by(Confirmation.numero)))


def summary(items: list[Confirmation]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for kind in ("banque", "client", "fournisseur", "avocat"):
        sent = [c for c in items if c.type == kind and c.statut != "a_envoyer"]
        received = [c for c in sent if c.statut == "recue"]
        amount = sum((abs(c.solde_comptable or ZERO) for c in sent), ZERO)
        confirmed = sum((abs(c.solde_comptable or ZERO) for c in received), ZERO)
        gaps = [
            c
            for c in received
            if c.solde_confirme is not None
            and c.solde_comptable is not None
            and c.solde_confirme != c.solde_comptable
        ]
        out[kind] = {
            "envoyees": len(sent),
            "recues": len(received),
            "taux_reponse": round(100 * len(received) / len(sent), 1) if sent else None,
            "montant_envoye": str(amount),
            "montant_recu": str(confirmed),
            "ecarts": len(gaps),
            "ecarts_non_expliques": sum(1 for c in gaps if not c.explication),
        }
    return out


@router.get("/audit-files/{file_id}/confirmations")
def list_confirmations(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    items = _file_confirmations(db, file.id)
    return {"confirmations": [conf_out(c) for c in items], "synthese": summary(items)}


@router.post("/audit-files/{file_id}/confirmations/select", status_code=201)
def select_parties(
    file_id: uuid.UUID, body: SelectIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    """Sélection : soldes au moins égaux au seuil (par défaut le seuil de planification), les
    plus importants d'abord ; toutes les banques. Un tiers déjà retenu n'est pas repris."""
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    rows = candidates(db, file, body.type)
    if body.type != "banque":
        threshold = body.seuil if body.seuil is not None else (file.seuil_planification or ZERO)
        rows = [r for r in rows if abs(r["solde"]) >= threshold and r["solde"] != 0]
    rows.sort(key=lambda r: -abs(r["solde"]))
    rows = rows[: body.maximum or get_settings().max_confirmations]
    existing = {(c.type, c.tiers) for c in _file_confirmations(db, file.id)}
    number = _next_number(db, file.id)
    added = 0
    for r in rows:
        if (body.type, r["tiers"]) in existing:
            continue
        db.add(
            Confirmation(
                engagement_id=file.engagement_id,
                audit_file_id=file.id,
                numero=number,
                type=body.type,
                tiers=str(r["tiers"])[:200],
                compte=r["compte"],
                solde_comptable=r["solde"],
            )
        )
        number += 1
        added += 1
    db.commit()
    return {"ajoutees": added, **list_confirmations(file_id, user, db)}


@router.post("/audit-files/{file_id}/confirmations", status_code=201)
def add_confirmation(
    file_id: uuid.UUID, body: ConfirmationIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    conf = Confirmation(
        engagement_id=file.engagement_id,
        audit_file_id=file.id,
        numero=_next_number(db, file.id),
        **body.model_dump(),
    )
    db.add(conf)
    db.commit()
    return conf_out(conf)


def _get(
    db: Session, conf_id: uuid.UUID, user: User, write: bool
) -> tuple[Confirmation, AuditFile]:
    conf = db.get(Confirmation, conf_id)
    if conf is None or conf.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Demande de confirmation introuvable")
    file, engagement = get_file(db, conf.audit_file_id, user)
    if write:
        require_work(file, engagement, user)
    return conf, file


@router.patch("/confirmations/{conf_id}")
def update_confirmation(
    conf_id: uuid.UUID, body: ConfirmationUpdate, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    conf, _ = _get(db, conf_id, user, write=True)
    data = body.model_dump(exclude_unset=True)
    if "solde_confirme" in data and data["solde_confirme"] is not None:
        data.setdefault("statut", "recue")
        data.setdefault("reponse_le", dt.date.today())
    if data.get("statut") == "envoyee" and conf.envoyee_le is None:
        data.setdefault("envoyee_le", dt.date.today())
    for key, value in data.items():
        setattr(conf, key, value)
    db.commit()
    return conf_out(conf)


@router.delete("/confirmations/{conf_id}", status_code=204)
def delete_confirmation(conf_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    conf, _ = _get(db, conf_id, user, write=True)
    if conf.statut != "a_envoyer":
        raise HTTPException(status.HTTP_409_CONFLICT, "Demande déjà envoyée : conservée")
    conf.deleted_at, conf.deleted_by = dt.datetime.now(dt.UTC), user.id
    db.commit()


@router.post("/confirmations/{conf_id}/reconcile")
def reconcile(conf_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Rapprochement automatique de l'écart par les lignes non lettrées du tiers."""
    conf, file = _get(db, conf_id, user, write=True)
    if conf.solde_confirme is None or conf.solde_comptable is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Réponse non saisie")
    gap = conf.solde_comptable - conf.solde_confirme
    if gap == 0:
        return {**conf_out(conf), "lignes": []}
    items = _ledger_items(db, file, ROOTS.get(conf.type, get_settings().racines_banques)) or []
    own = [
        i
        for i in items
        if (i.tiers or i.compte) == conf.tiers or (not i.tiers and i.compte == conf.compte)
    ]
    found = letters.explain(gap, own, SIGN[conf.type])
    if found is None:
        return {
            **conf_out(conf),
            "lignes": [],
            "message": "Écart non expliqué par les écritures en suspens",
        }
    detail = ", ".join(
        f"{i.piece or '?'} du {i.date:%d/%m/%Y} ({SIGN[conf.type] * i.net:,.0f})".replace(",", " ")
        for i in found
    )
    conf.explication = f"Écart expliqué automatiquement par les écritures en suspens : {detail}."
    db.commit()
    return {
        **conf_out(conf),
        "lignes": [
            {
                "piece": i.piece,
                "date": i.date.isoformat() if i.date else None,
                "montant": str(SIGN[conf.type] * i.net),
            }
            for i in found
        ],
    }


def _letters_response(
    db: Session, file: AuditFile, items: list[Confirmation], fmt: str
) -> Response:
    entity = db.get(AuditableEntity, file.entity_id).nom
    rendered = [letters.render(c, entity, file.date_fin, file.devise) for c in items]
    content = letters.to_pdf(rendered) if fmt == "pdf" else letters.to_docx(rendered)
    record_event(
        db,
        "export",
        object_type="AuditFile",
        object_id=file.id,
        details={"circularisation": fmt, "lettres": len(items)},
    )
    db.commit()
    name = (
        f"circularisation_{file.exercice}.{fmt}"
        if len(items) > 1
        else f"{f'CIRC-{items[0].numero:03d}'}.{fmt}"
    )
    return Response(
        content,
        media_type=MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/confirmations/{conf_id}/letter")
def letter(
    conf_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    conf, file = _get(db, conf_id, user, write=False)
    return _letters_response(db, file, [conf], format)


@router.get("/audit-files/{file_id}/confirmations/letters")
def all_letters(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),  # noqa: A002
    type: str | None = Query(None, pattern=TYPES),
) -> Response:  # noqa: A002
    """Lettres des demandes à envoyer (toutes, ou d'un type)."""
    file, _ = get_file(db, file_id, user)
    items = [c for c in _file_confirmations(db, file.id, type) if c.statut == "a_envoyer"]
    if not items:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucune demande à envoyer")
    return _letters_response(db, file, items, format)
