"""Modèles de mission : programmes de travail types (AUD-09)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, require
from app.api.library import linked_controls, procedures_by_control, set_links
from app.api.mission_access import get_engagement
from app.api.program import CONTROL_FIELDS, RISK_FIELDS, add_procedure
from app.models.engagement import Engagement
from app.models.program import Control, EngagementTemplate, Risk
from app.models.user import User
from app.schemas_mission import TemplateIn, TemplateOut, TemplateUpdate
from app.security.roles import Perm

router = APIRouter(prefix="/templates", tags=["Modèles de mission"])
Reader = Annotated[User, Depends(require(Perm.MISSIONS_READ_ALL, Perm.MISSIONS_READ_OWN))]
Manager = Annotated[User, Depends(require(Perm.MISSIONS_MANAGE))]


def snapshot(db: Session, risks: list[Risk]) -> dict[str, Any]:
    """Fige risques, contrôles liés et procédures ; un contrôle partagé n'apparaît qu'une fois."""
    links = linked_controls(db, [r.id for r in risks])
    controls: dict[uuid.UUID, Control] = {c.id: c for cs in links.values() for c in cs}
    procedures = procedures_by_control(db, list(controls))
    return {
        "risques": [
            {
                **{f: getattr(r, f) for f in RISK_FIELDS},
                "source_id": str(r.source_id or r.id) if r.bibliotheque or r.source_id else None,
                "controles": [str(c.id) for c in links[r.id]],
            }
            for r in risks
        ],
        "controles": [
            {
                "cle": str(c.id),
                **{f: getattr(c, f) for f in CONTROL_FIELDS},
                "source_id": str(c.source_id or c.id) if c.bibliotheque or c.source_id else None,
                "procedures": [
                    {"description": p.description, "type_test": p.type_test}
                    for p in procedures[c.id]
                ],
            }
            for c in controls.values()
        ],
    }


def instantiate(db: Session, template: EngagementTemplate, engagement: Engagement) -> None:
    """Crée dans la mission la matrice décrite par le modèle."""
    created: dict[str, Control] = {}
    for c in template.contenu.get("controles", []):
        control = Control(
            **{f: c[f] for f in CONTROL_FIELDS},
            bibliotheque=False,
            engagement_id=engagement.id,
            source_id=uuid.UUID(c["source_id"]) if c.get("source_id") else None,
        )
        db.add(control)
        db.flush()
        for p in c.get("procedures", []):
            add_procedure(db, engagement, control, p["description"], p["type_test"])
        created[c["cle"]] = control
    for r in template.contenu.get("risques", []):
        risk = Risk(
            **{f: r[f] for f in RISK_FIELDS},
            bibliotheque=False,
            engagement_id=engagement.id,
            source_id=uuid.UUID(r["source_id"]) if r.get("source_id") else None,
        )
        db.add(risk)
        db.flush()
        set_links(db, risk, [created[k].id for k in r.get("controles", []) if k in created])


def get_template(db: Session, template_id: uuid.UUID) -> EngagementTemplate:
    template = db.scalar(
        select(EngagementTemplate).where(
            EngagementTemplate.id == template_id, EngagementTemplate.deleted_at.is_(None)
        )
    )
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modèle introuvable")
    return template


def template_out(t: EngagementTemplate) -> TemplateOut:
    controls = t.contenu.get("controles", [])
    return TemplateOut.model_validate(
        {
            **{k: getattr(t, k) for k in TemplateOut.model_fields if hasattr(t, k)},
            "nb_risques": len(t.contenu.get("risques", [])),
            "nb_controles": len(controls),
            "nb_procedures": sum(len(c.get("procedures", [])) for c in controls),
        }
    )


@router.get("", response_model=list[TemplateOut])
def list_templates(_: Reader, db: DbSession) -> list[TemplateOut]:
    rows = db.scalars(
        select(EngagementTemplate)
        .where(EngagementTemplate.deleted_at.is_(None))
        .order_by(EngagementTemplate.nom)
    )
    return [template_out(t) for t in rows]


@router.get("/{template_id}", response_model=TemplateOut)
def read_template(template_id: uuid.UUID, _: Reader, db: DbSession) -> TemplateOut:
    return template_out(get_template(db, template_id))


@router.post("", response_model=TemplateOut, status_code=201)
def create_template(body: TemplateIn, user: Manager, db: DbSession) -> TemplateOut:
    """Modèle tiré du programme d'une mission existante, ou de risques de la bibliothèque."""
    if db.scalar(select(EngagementTemplate.id).where(EngagementTemplate.nom == body.nom)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Un modèle porte déjà ce nom")
    if body.from_engagement_id:
        engagement = get_engagement(db, body.from_engagement_id, user)
        risks = list(
            db.scalars(
                select(Risk)
                .where(Risk.engagement_id == engagement.id, Risk.deleted_at.is_(None))
                .order_by(Risk.cycle, Risk.created_at)
            )
        )
        defaults = {
            "perimetre": engagement.perimetre,
            "objectifs": engagement.objectifs,
            "budget_jours": engagement.budget_jours,
        }
    else:
        risks = list(
            db.scalars(
                select(Risk)
                .where(
                    Risk.id.in_(body.library_risk_ids),
                    Risk.bibliotheque.is_(True),
                    Risk.deleted_at.is_(None),
                )
                .order_by(Risk.cycle, Risk.libelle)
            )
        )
        if len(risks) != len(set(body.library_risk_ids)):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND, "Risque introuvable dans la bibliothèque"
            )
        defaults = {}
    if not risks:
        raise HTTPException(422, "Le modèle doit contenir au moins un risque")
    template = EngagementTemplate(
        nom=body.nom,
        description=body.description,
        perimetre=body.perimetre or defaults.get("perimetre"),
        objectifs=body.objectifs or defaults.get("objectifs"),
        budget_jours=body.budget_jours or defaults.get("budget_jours"),
        contenu=snapshot(db, risks),
    )
    db.add(template)
    db.commit()
    return template_out(template)


@router.patch("/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: uuid.UUID, body: TemplateUpdate, _: Manager, db: DbSession
) -> TemplateOut:
    template = get_template(db, template_id)
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None or key != "nom":
            setattr(template, key, value)
    db.commit()
    return template_out(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: uuid.UUID, user: Manager, db: DbSession) -> None:
    template = get_template(db, template_id)
    template.deleted_at = datetime.now(UTC)
    template.deleted_by = user.id
    db.commit()
