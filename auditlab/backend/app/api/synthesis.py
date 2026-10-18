"""Note de synthèse générée (REV-26) : travaux par cycle, anomalies, points en suspens,
conclusion. Chaque point en suspens renvoie à l'écran du dossier qui permet de le lever."""

import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import adjustments as adj_api
from app.api import analytical, third_parties
from app.api.audit_files import get_file, require_direct
from app.api.bank_reconciliations import overview as bank_overview
from app.api.confirmations import _file_confirmations
from app.api.confirmations import summary as confirmation_summary
from app.api.deps import CurrentUser, DbSession
from app.api.lead_schedules import lead_schedules
from app.api.signoffs import signoffs_by_workpaper, status_of
from app.audit.listeners import record_event
from app.models.revision import AuditFile
from app.models.universe import AuditableEntity
from app.models.user import User
from app.models.workpaper import ReviewNote, Workpaper
from app.revision import documents, statements
from app.revision.mapping import UnmappedError, assignments, unmapped

router = APIRouter(tags=["Révision – note de synthèse"])
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ConclusionIn(BaseModel):
    conclusion: str = Field(min_length=10, max_length=20000)


def _fr(value: Any) -> str:
    return f"{Decimal(value):,.0f}".replace(",", " ")


def _optional(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except (HTTPException, UnmappedError):
        return None


def build(db: Session, file: AuditFile, user: User) -> dict[str, Any]:
    pending: list[dict[str, str]] = []

    def add(vue: str, texte: str) -> None:
        pending.append({"vue": vue, "texte": texte})

    missing = unmapped(assignments(db, file))
    if missing:
        add(
            "affectation",
            f"{len(missing)} compte(s) non affecté(s) : aucun état ne peut être produit",
        )
    review = _optional(analytical.review, db, file)
    if review is None:
        add("planification", "Seuil de signification non fixé ou revue analytique impossible")
    elif review["nb_non_justifies"]:
        add(
            "analytique",
            f"{review['nb_non_justifies']} variation(s) significative(s) non justifiée(s)",
        )
    tiers = _optional(third_parties.justification, file.id, user, db)
    if tiers and tiers["non_justifies"]:
        add("tiers", f"{tiers['non_justifies']} compte(s) de tiers non justifié(s)")
    stats = confirmation_summary(_file_confirmations(db, file.id))
    names = {
        "banque": "des banques",
        "client": "des clients",
        "fournisseur": "des fournisseurs",
        "avocat": "des avocats",
    }
    for kind, s in stats.items():
        if s["envoyees"] > s["recues"]:
            add(
                "circularisation",
                f"Circularisation {names[kind]} : "
                f"{s['envoyees'] - s['recues']} réponse(s) manquante(s)",
            )
        if s["ecarts_non_expliques"]:
            add(
                "circularisation",
                f"Circularisation {names[kind]} : "
                f"{s['ecarts_non_expliques']} écart(s) non expliqué(s)",
            )
    bank = bank_overview(db, file)
    for r in bank["rapprochements"]:
        for a in r["anomalies"]:
            add("tresorerie", f"Rapprochement {r['compte']} : {a}")
    if bank["comptes_sans_rapprochement"]:
        add(
            "tresorerie",
            "Comptes sans rapprochement : " + ", ".join(bank["comptes_sans_rapprochement"]),
        )
    states = _optional(statements.build, db, file)
    for c in (states or {}).get("controles", []):
        if not c["ok"]:
            add("etats", f"Contrôle des états en écart : {c['libelle']}")
    items = adj_api.file_adjustments(db, file.id)
    proposed = [a for a in items if a.statut == "proposee"]
    if proposed:
        add(
            "ajustements",
            f"{len(proposed)} écriture(s) d'ajustement en attente de la décision de l'entité",
        )
    papers = list(
        db.scalars(
            select(Workpaper).where(
                Workpaper.engagement_id == file.engagement_id, Workpaper.deleted_at.is_(None)
            )
        )
    )
    signoffs = signoffs_by_workpaper(db, [p.id for p in papers])
    status = {p.id: status_of(signoffs[p.id]) for p in papers}
    not_approved = [p.reference for p in papers if status[p.id] != "approuve"]
    if not_approved:
        add("cycles", "Papiers de travail non approuvés : " + ", ".join(sorted(not_approved)))
    notes = db.scalar(
        select(func.count())
        .select_from(ReviewNote)
        .where(
            ReviewNote.engagement_id == file.engagement_id,
            ReviewNote.statut == "ouverte",
            ReviewNote.deleted_at.is_(None),
        )
    )
    if notes:
        add("cycles", f"{notes} note(s) de revue ouverte(s)")
    lines = adj_api.lines_of(db, [a.id for a in items])
    accepted = [a for a in items if a.statut == "acceptee"]
    uncorrected = _optional(adj_api.unadjusted, file.id, user, db)
    return {
        "cycles": [
            {
                "cycle": s["libelle"],
                "N-1": s["totaux"]["N-1"],
                "N": s["totaux"]["N"],
                "ajustements": s["totaux"]["ajustements"],
                "revise": s["totaux"]["revise"],
                "papiers": [
                    {
                        "reference": p["reference"],
                        "titre": p["titre"],
                        "statut": status.get(uuid.UUID(p["id"]), "brouillon"),
                    }
                    for p in s["papiers"]
                ],
            }
            for s in lead_schedules(db, file)
        ],
        "ajustements_acceptes": [
            {
                "numero": a.numero,
                "libelle": a.libelle,
                "effet_resultat": str(adj_api.result_effect(lines[a.id])),
            }
            for a in accepted
        ],
        "non_corrigees": uncorrected,
        "seuils": {
            k: str(getattr(file, k)) if getattr(file, k) is not None else None
            for k in ("seuil_signification", "seuil_planification", "seuil_insignifiant")
        },
        "points_en_suspens": pending,
        "conclusion": file.conclusion_synthese,
    }


def blocks(data: dict[str, Any], file: AuditFile, entity: str) -> list[dict[str, Any]]:
    s = data["seuils"]
    out: list[dict[str, Any]] = [
        {"texte": f"Entité : {entity} — exercice clos le {file.date_fin:%d/%m/%Y} ({file.devise})"},
        {"titre": "1. Seuils retenus"},
        {
            "texte": (
                f"Seuil de signification : {_fr(s['seuil_signification'])} ; planification : "
                f"{_fr(s['seuil_planification'])} ; anomalies manifestement insignifiantes : "
                f"{_fr(s['seuil_insignifiant'])}."
            )
            if s["seuil_signification"]
            else "Seuil non fixé."
        },
        {"titre": "2. Travaux par cycle"},
        {
            "tableau": [["Cycle", "N-1", "N", "Ajustements", "Révisé", "Papiers"]]
            + [
                [
                    c["cycle"],
                    _fr(c["N-1"]),
                    _fr(c["N"]),
                    _fr(c["ajustements"]),
                    _fr(c["revise"]),
                    ", ".join(f"{p['reference']} ({p['statut']})" for p in c["papiers"]) or "—",
                ]
                for c in data["cycles"]
            ]
        },
        {"titre": "3. Anomalies"},
    ]
    if data["ajustements_acceptes"]:
        out.append({"texte": "Ajustements acceptés par l'entité :"})
        out.append(
            {
                "liste": [
                    f"AJE {a['numero']} — {a['libelle']} "
                    f"(effet sur le résultat {_fr(a['effet_resultat'])})"
                    for a in data["ajustements_acceptes"]
                ]
            }
        )
    nc = data["non_corrigees"]
    if nc:
        verdict = {
            "non_significatif": "inférieur au seuil de planification",
            "vigilance": "entre le seuil de planification et le seuil de signification",
            "significatif": "significatif",
        }[nc["conclusion"]]
        out.append(
            {
                "texte": f"Anomalies non corrigées : cumul de {_fr(nc['cumul_resultat'])} "
                f"sur le résultat, {verdict}."
            }
        )
    out += [
        {"titre": "4. Points en suspens"},
        {"liste": [p["texte"] for p in data["points_en_suspens"]]}
        if data["points_en_suspens"]
        else {"texte": "Aucun point en suspens."},
        {"titre": "5. Conclusion"},
        {"texte": data["conclusion"] or "Conclusion à rédiger par le chef de mission."},
    ]
    return out


@router.get("/audit-files/{file_id}/synthesis")
def read_synthesis(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return build(db, file, user)


@router.put("/audit-files/{file_id}/synthesis/conclusion")
def set_conclusion(
    file_id: uuid.UUID, body: ConclusionIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_direct(file, engagement, user)
    file.conclusion_synthese = body.conclusion
    db.commit()
    return build(db, file, user)


@router.get("/audit-files/{file_id}/synthesis/export")
def export_synthesis(
    file_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
) -> Response:  # noqa: A002
    file, _ = get_file(db, file_id, user)
    entity = db.get(AuditableEntity, file.entity_id).nom
    content = documents.render(
        format,
        f"Note de synthèse – exercice {file.exercice}",
        blocks(build(db, file, user), file, entity),
    )
    record_event(
        db, "export", object_type="AuditFile", object_id=file.id, details={"note_synthese": format}
    )
    db.commit()
    return Response(
        content,
        media_type=MEDIA[format],
        headers={
            "Content-Disposition": f'attachment; filename="note_synthese_{file.exercice}.{format}"'
        },
    )
