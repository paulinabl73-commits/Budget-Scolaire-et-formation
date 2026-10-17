"""Preuves des constats (CON-03) : papiers, pièces jointes et résultats d'analyse."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession
from app.api.findings import get_finding, require_writer
from app.models.data import Dataset
from app.models.finding import Criticality, Finding, FindingEvidence, FindingStatus
from app.models.workpaper import Attachment, Workpaper
from app.schemas_finding import EvidenceIn, EvidenceOut, FindingOut

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


MAX_LINES = 200


class LinesToFindingIn(BaseModel):
    titre: str = Field(min_length=1, max_length=300)
    criticite: Criticality = Criticality.MOYENNE
    lignes: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_LINES)
    commentaire: str | None = Field(default=None, max_length=4000)
    finding_id: uuid.UUID | None = None  # pour compléter un constat existant


def _as_text(value: Any) -> str | None:
    """Valeur telle que la grille la reçoit, ramenée au texte DuckDB pour comparaison."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if len(text) >= 19 and text[10] == "T" and text[4] == "-":  # date et heure ISO
        text = text.replace("T", " ")
    return text


@router.post(
    "/datasets/{dataset_id}/findings",
    response_model=FindingOut,
    status_code=status.HTTP_201_CREATED,
)
def lines_to_finding(
    dataset_id: uuid.UUID, body: LinesToFindingIn, user: CurrentUser, db: DbSession
) -> FindingOut:
    """DAT-31 : des lignes d'anomalie deviennent un constat, avec leurs données en preuve.

    Chaque ligne envoyée est recherchée dans la table : seules des lignes réellement présentes
    peuvent servir de preuve.
    """
    from app.analytics.relation import RelationError, evaluate, relation
    from app.analytics.store import quote_ident
    from app.api.datasets import get_dataset
    from app.api.findings import _next_reference, finding_out

    ds, engagement = get_dataset(db, dataset_id, user)
    require_writer(engagement, user)
    rel = relation(db, ds)
    columns = [c["nom"] for c in rel.schema]
    rows: list[list[Any]] = []
    for line in body.lignes:
        if set(line) - set(columns):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Colonne inconnue")
        values = [line.get(c) for c in columns]
        where = " AND ".join(
            f"CAST({quote_ident(c)} AS VARCHAR) IS NOT DISTINCT FROM ?"
            for c in columns
            if c in line
        )
        params = [_as_text(line[c]) for c in columns if c in line]
        try:
            found = evaluate(rel, f"SELECT count(*) FROM t WHERE {where}", params).item()  # noqa: S608
        except RelationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        if not found:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Une ligne n'existe pas dans la table"
            )
        rows.append(values)
    if body.finding_id:
        finding, _ = get_finding(db, body.finding_id, user)
        if finding.engagement_id != engagement.id:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Constat d'une autre mission"
            )
        require_open_finding(finding)
    else:
        finding = Finding(
            engagement_id=engagement.id,
            reference=_next_reference(db, engagement),
            titre=body.titre,
            criticite=body.criticite.value,
            constat=f"{len(rows)} ligne(s) de la table « {ds.nom} » présentent l'anomalie "
            "(détail en preuve).",
        )
        db.add(finding)
        db.flush()
    db.add(
        FindingEvidence(
            engagement_id=engagement.id,
            finding_id=finding.id,
            type="lignes",
            dataset_id=ds.id,
            empreinte=ds.parquet_sha256,
            extrait={"colonnes": columns, "lignes": rows, "nb_lignes": len(rows)},
            commentaire=body.commentaire,
        )
    )
    db.commit()
    return finding_out(db, finding, engagement, user)
