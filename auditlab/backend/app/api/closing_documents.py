"""RCO-25 : documents de la clôture à partir de modèles paramétrables (REV-27).

Attestation de présentation des comptes, lettre de mission, lettre de recommandations et
note de synthèse : modèles du Module 5 (codes de `documents_cloture.json`) alimentés par les
données du client et les états révisés du dossier. L'attestation est signée par
l'expert-comptable, après son visa de revue (RCO-23) ; l'empreinte du contenu signé permet
de détecter une modification ultérieure du dossier.
"""

import datetime as dt
import hashlib
import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.adjustments import file_adjustments
from app.api.closing_review import blockers
from app.api.deps import CurrentUser, DbSession
from app.api.opinion import MEDIA
from app.api.pieces import _closing, _require_team
from app.api.portfolio import can_manage_client
from app.audit.listeners import record_event
from app.config import get_settings
from app.models.portfolio import Client, Closing
from app.models.revision import AccountingFramework, AuditFile, ReportTemplate
from app.models.user import User
from app.revision import documents, reports
from app.revision.formula import evaluate
from app.revision.mapping import UnmappedError, file_values

router = APIRouter(tags=["Portefeuille (Module 6)"])
CODES = ("presentation", "lettre_mission_cloture", "recommandations", "note_cloture")
SIGNED = "presentation"


class Recommendation(BaseModel):
    constat: str = Field(min_length=3, max_length=2000)
    recommandation: str = Field(min_length=3, max_length=2000)


class ParametersIn(BaseModel):
    lieu: str | None = Field(default=None, max_length=120)
    honoraires: str | None = Field(default=None, max_length=500)
    observations: str | None = Field(default=None, max_length=10000)
    recommandations: list[Recommendation] = Field(default_factory=list, max_length=100)


def _template(db: Session, code: str) -> ReportTemplate:
    t = db.scalar(
        select(ReportTemplate).where(
            ReportTemplate.code == code, ReportTemplate.deleted_at.is_(None)
        )
    )
    if code not in CODES or t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle introuvable")
    return t


def _name(db: Session, user_id: uuid.UUID | None) -> str:
    return db.get(User, user_id).nom if user_id else "—"


def _recommendations(items: list[dict[str, str]]) -> str:
    if not items:
        return "Aucune recommandation particulière."
    return "\n".join(
        f"{i}. {r['constat']} — Recommandation : {r['recommandation']}"
        for i, r in enumerate(items, 1)
    )


def _visas(revues: dict[str, Any]) -> str:
    if not revues:
        return "Dossier non encore revu."
    labels = {"superviseur": "Superviseur", "expert": "Expert-comptable"}
    return "\n".join(
        f"{labels[k]} : {v['par']}, le {v['le'][:10]}" for k, v in revues.items() if k in labels
    )


def context(db: Session, closing: Closing, client: Client) -> dict[str, str]:
    file = db.get(AuditFile, closing.audit_file_id)
    fw = db.get(AccountingFramework, file.framework_id)
    try:
        values = file_values(db, file, adjusted=True)["N"]
    except UnmappedError:
        values = None
    bases = {b["code"]: b["formule"] for b in fw.bases_seuil}

    def base(code: str) -> str:
        if values is None or code not in bases:
            return "—"
        return reports.amount(evaluate(bases[code], values) or Decimal(0))

    params = closing.documents or {}
    signature = params.get("signature") or {}
    accepted = [
        a
        for a in file_adjustments(db, file.id)
        if a.type == "inventaire" and a.statut == "acceptee"
    ]
    pending = blockers(db, closing, client, "expert")
    return {
        "entite": client.raison_sociale,
        "forme_juridique": client.forme_juridique,
        "rccm": client.rccm or "—",
        "identifiant_fiscal": client.identifiant_fiscal or "—",
        "exercice": str(closing.exercice),
        "date_cloture": file.date_fin.strftime("%d/%m/%Y"),
        "referentiel": fw.libelle,
        **{k: base(k) for k in ("total_bilan", "capitaux_propres", "resultat", "chiffre_affaires")},
        "devise": file.devise,
        "cabinet": get_settings().nom_cabinet,
        "expert": _name(db, client.expert_id),
        "collaborateur": _name(db, client.collaborateur_id),
        "lieu": params.get("lieu") or "",
        "date": (
            dt.datetime.fromisoformat(signature["le"]) if signature else dt.datetime.now(dt.UTC)
        ).strftime("%d/%m/%Y"),
        "honoraires": params.get("honoraires") or "à convenir",
        "observations": params.get("observations") or "",
        "recommandations": _recommendations(params.get("recommandations", [])),
        "ecritures": " ; ".join(a.libelle for a in accepted) or "aucune",
        "points_suspens": "\n".join(f"• {p}" for p in pending) or "Aucun point en suspens.",
        "visas": _visas(closing.revues or {}),
    }


def _blocks(db: Session, closing: Closing, client: Client, code: str) -> list[dict[str, Any]]:
    params = closing.documents or {}
    holder = SimpleNamespace(observations=params.get("observations"), type_opinion=None)
    return reports.blocks(_template(db, code), holder, context(db, closing, client))


def _fingerprint(blocks: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        json.dumps(blocks, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def overview(db: Session, closing: Closing, client: Client, user: User) -> dict[str, Any]:
    params = closing.documents or {}
    signature = params.get("signature")
    if signature:
        current = _fingerprint(_blocks(db, closing, client, SIGNED))
        signature = {**signature, "conforme": current == signature["empreinte"]}
    names = {
        t.code: t.nom
        for t in db.scalars(select(ReportTemplate).where(ReportTemplate.code.in_(CODES)))
    }
    return {
        "parametres": {k: params.get(k) for k in ("lieu", "honoraires", "observations")}
        | {"recommandations": params.get("recommandations", [])},
        "modeles": [{"code": c, "nom": names[c]} for c in CODES if c in names],
        "signature": signature,
        "peut_signer": can_manage_client(client, user),
        "visa_expert": "expert" in (closing.revues or {}),
    }


@router.get("/closings/{closing_id}/documents")
def read_documents(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    return overview(db, closing, client, user)


@router.put("/closings/{closing_id}/documents")
def save_parameters(
    closing_id: uuid.UUID, body: ParametersIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    _require_team(client, user)
    params = closing.documents or {}
    data = body.model_dump()
    if params.get("signature") and any(data[k] != params.get(k) for k in ("lieu", "observations")):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Attestation signée : annulez la signature pour la modifier"
        )
    closing.documents = {**params, **data}
    db.commit()
    return overview(db, closing, client, user)


@router.get("/closings/{closing_id}/documents/{code}")
def download(
    closing_id: uuid.UUID,
    code: str,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    closing, client = _closing(db, closing_id, user)
    t = _template(db, code)
    title = f"{t.nom} – exercice {closing.exercice}"
    if code == SIGNED and not (closing.documents or {}).get("signature"):
        title = f"PROJET – {title}"
    content = documents.render(format, title, _blocks(db, closing, client, code))
    record_event(
        db, "export", object_type="Closing", object_id=closing.id, details={"document": code}
    )
    db.commit()
    return Response(
        content,
        media_type=MEDIA[format],
        headers={
            "Content-Disposition": f'attachment; filename="{code}_{closing.exercice}.{format}"'
        },
    )


@router.post("/closings/{closing_id}/documents/presentation/sign")
def sign(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    if not can_manage_client(client, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Signature réservée à l'expert-comptable")
    params = closing.documents or {}
    if params.get("signature"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Attestation déjà signée")
    if "expert" not in (closing.revues or {}):
        raise HTTPException(status.HTTP_409_CONFLICT, "Visa de revue de l'expert-comptable attendu")
    signature = {"le": dt.datetime.now(dt.UTC).isoformat(), "par": user.nom}
    closing.documents = {**params, "signature": signature}
    signature["empreinte"] = _fingerprint(_blocks(db, closing, client, SIGNED))
    closing.documents = {**params, "signature": signature}
    record_event(db, "signature", object_type="Closing", object_id=closing.id,
                 details={"document": SIGNED, "empreinte": signature["empreinte"]})  # fmt: skip
    db.commit()
    return overview(db, closing, client, user)


@router.delete("/closings/{closing_id}/documents/presentation/sign")
def unsign(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, client = _closing(db, closing_id, user)
    if not can_manage_client(client, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'expert-comptable")
    if closing.date_depot is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Comptes déjà déposés")
    closing.documents = {k: v for k, v in (closing.documents or {}).items() if k != "signature"}
    db.commit()
    return overview(db, closing, client, user)
