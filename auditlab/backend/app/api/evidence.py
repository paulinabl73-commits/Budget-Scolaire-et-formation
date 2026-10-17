"""Preuves des constats (CON-03) : papiers, pièces jointes et résultats d'analyse."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.findings import get_finding, require_writer
from app.models.data import Dataset
from app.models.finding import Finding, FindingEvidence, FindingStatus
from app.models.workpaper import Attachment, Workpaper
from app.schemas_finding import EvidenceIn, EvidenceOut

router = APIRouter(tags=["Constats"])


def evidence_out(db: Session, e: FindingEvidence) -> EvidenceOut:
    out = EvidenceOut.model_validate(e)
    if e.workpaper_id:
        wp = db.get(Workpaper, e.workpaper_id)
        out.libelle = f"{wp.reference} · {wp.titre}"
    if e.attachment_id:
        att = db.get(Attachment, e.attachment_id)
        out.libelle = att.nom_fichier
        out.empreinte_actuelle = att.sha256
    if e.dataset_id:
        ds = db.get(Dataset, e.dataset_id)
        out.libelle = ds.nom
        out.empreinte_actuelle = ds.parquet_sha256
    return out


def require_open_finding(finding: Finding) -> None:
    if finding.statut == FindingStatus.VALIDE.value:
        raise HTTPException(status.HTTP_409_CONFLICT, "Constat validé : preuves figées")


def add_evidence(db: Session, finding: Finding, body: EvidenceIn) -> FindingEvidence:
    """Contrôle que l'élément appartient à la mission et fige son empreinte."""
    ev = FindingEvidence(
        engagement_id=finding.engagement_id, finding_id=finding.id, type=body.type,
        commentaire=body.commentaire,
    )  # fmt: skip
    if body.type == "papier":
        wp = db.get(Workpaper, body.workpaper_id) if body.workpaper_id else None
        if wp is None or wp.engagement_id != finding.engagement_id or wp.deleted_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Papier de travail inconnu")
        ev.workpaper_id = wp.id
    elif body.type == "piece_jointe":
        att = db.get(Attachment, body.attachment_id) if body.attachment_id else None
        if att is None or att.engagement_id != finding.engagement_id or att.deleted_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pièce jointe inconnue")
        ev.attachment_id, ev.workpaper_id, ev.empreinte = att.id, att.workpaper_id, att.sha256
    else:
        ds = db.get(Dataset, body.dataset_id) if body.dataset_id else None
        if ds is None or ds.engagement_id != finding.engagement_id or ds.deleted_at:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Table inconnue")
        ev.dataset_id, ev.empreinte = ds.id, ds.parquet_sha256
        ev.extrait = {"nb_lignes": ds.nb_lignes, "operation": ds.operation or ds.kind}
    db.add(ev)
    return ev


@router.get("/findings/{finding_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(finding_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[EvidenceOut]:
    finding, _ = get_finding(db, finding_id, user)
    rows = db.scalars(
        select(FindingEvidence)
        .where(FindingEvidence.finding_id == finding.id, FindingEvidence.deleted_at.is_(None))
        .order_by(FindingEvidence.created_at)
    )
    return [evidence_out(db, e) for e in rows]


@router.post(
    "/findings/{finding_id}/evidence",
    response_model=EvidenceOut,
    status_code=status.HTTP_201_CREATED,
)
def create_evidence(
    finding_id: uuid.UUID, body: EvidenceIn, user: CurrentUser, db: DbSession
) -> EvidenceOut:
    finding, engagement = get_finding(db, finding_id, user)
    require_writer(engagement, user)
    require_open_finding(finding)
    ev = add_evidence(db, finding, body)
    db.commit()
    return evidence_out(db, ev)


@router.delete("/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(evidence_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    ev = db.scalar(
        select(FindingEvidence).where(
            FindingEvidence.id == evidence_id, FindingEvidence.deleted_at.is_(None)
        )
    )
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Preuve introuvable")
    finding, engagement = get_finding(db, ev.finding_id, user)
    require_writer(engagement, user)
    require_open_finding(finding)
    ev.deleted_at, ev.deleted_by = datetime.now(UTC), user.id
    db.commit()
