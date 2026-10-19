"""Contenu du rapport de mission (REP-02), décrit en blocs (`revision/documents`) selon le
modèle (REP-01) : page de garde, synthèse, contexte, constats avec réponses des audités et
plans d'action, tableau des plans d'action, annexes.

Seuls les constats validés (fin de la phase contradictoire, CON-04) sont rapportés ; un
projet signale ceux qui ne le sont pas encore.
"""

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.engagement import Engagement
from app.models.finding import CRITICALITY_ORDER, ActionPlan, Finding, FindingStatus
from app.models.report import MissionReport, MissionReportTemplate
from app.models.user import User
from app.models.workpaper import Workpaper
from app.storage import get_storage

CRITICITE = {"faible": "Faible", "moyenne": "Moyenne", "elevee": "Élevée", "critique": "Critique"}
POSITION = {"accord": "Accord", "accord_partiel": "Accord partiel", "desaccord": "Désaccord",
            "sans_reponse": "Pas de réponse dans le délai"}  # fmt: skip
PLAN_STATUT = {"a_lancer": "À lancer", "en_cours": "En cours", "realise": "Réalisé",
               "verifie": "Vérifié", "risque_accepte": "Risque accepté"}  # fmt: skip
PLAN_HEADER = ["Constat", "Plan d'action", "Responsable", "Échéance", "Statut"]
ROLE = {"chef_mission": "Chef de mission", "auditeur": "Auditeur",
        "data_analyst": "Data analyst", "superviseur": "Superviseur"}  # fmt: skip


class _Values(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def ordered(findings: list[Finding], order: str) -> list[Finding]:
    rank = {c.value: i for i, c in enumerate(CRITICALITY_ORDER)}
    if order == "reference":
        return sorted(findings, key=lambda f: f.reference)
    reverse = order == "criticite_decroissante"
    return sorted(
        findings, key=lambda f: (-rank[f.criticite] if reverse else rank[f.criticite], f.reference)
    )


def _name(db: Session, user_id: Any) -> str:
    return db.get(User, user_id).nom if user_id else "—"


def build(
    db: Session, engagement: Engagement, report: MissionReport, template: MissionReportTemplate
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Titre, blocs et pied de page du rapport."""
    entity = engagement.entity.nom if engagement.entity else "—"
    today = dt.date.today().strftime("%d/%m/%Y")
    values = _Values(mission=engagement.titre, reference=engagement.reference, entite=entity,
                     date=today)  # fmt: skip
    all_findings = list(
        db.scalars(
            select(Finding).where(
                Finding.engagement_id == engagement.id, Finding.deleted_at.is_(None)
            )
        )
    )
    findings = ordered(
        [f for f in all_findings if f.statut == FindingStatus.VALIDE.value],
        template.ordre_constats,
    )
    plans: dict[Any, list[ActionPlan]] = {f.id: [] for f in findings}
    if findings:
        for p in db.scalars(
            select(ActionPlan)
            .where(ActionPlan.finding_id.in_(list(plans)), ActionPlan.deleted_at.is_(None))
            .order_by(ActionPlan.echeance)
        ):
            plans[p.finding_id].append(p)

    cover = template.page_garde or {}
    blocks: list[dict[str, Any]] = []
    if template.logo_storage_key:
        blocks.append({"image": b"".join(get_storage().open(template.logo_storage_key)),
                       "largeur_mm": 40})  # fmt: skip
    for key, size in (("organisation", 12), ("titre", 24), ("sous_titre", 14)):
        if cover.get(key):
            blocks.append({"garde": cover[key].format_map(values), "taille": size})
    blocks.append({"garde": f"{entity} – {today}", "taille": 11})
    if cover.get("mention"):
        blocks.append({"garde": cover["mention"].format_map(values), "taille": 9})
    blocks.append({"saut": True})

    pending = [f.reference for f in all_findings if f.statut != FindingStatus.VALIDE.value]
    if pending:
        blocks.append({"texte": f"PROJET – constats en phase contradictoire non repris : "
                                f"{', '.join(sorted(pending))}."})  # fmt: skip

    def plan_row(f: Finding, p: ActionPlan) -> list[str]:
        who = p.responsable_nom or _name(db, p.responsable_id)
        return [f.reference, p.description, who, p.echeance.strftime("%d/%m/%Y"),
                PLAN_STATUT.get(p.statut, p.statut)]  # fmt: skip

    for section in template.sections:
        if not section.get("actif", True):
            continue
        code = section["code"]
        blocks.append({"titre": section["titre"], "niveau": 1})
        if code == "synthese":
            blocks.append({"texte": report.synthese or "Synthèse à rédiger."})
            counts = [[CRITICITE[c.value], str(sum(f.criticite == c.value for f in findings))]
                      for c in reversed(CRITICALITY_ORDER)]  # fmt: skip
            blocks.append({"tableau": [["Criticité", "Constats"], *counts], "entete": True})
            if report.conclusion:
                blocks += [{"titre": "Conclusion", "niveau": 2}, {"texte": report.conclusion}]
        elif code == "contexte":
            blocks.append({"texte": f"Mission {engagement.reference} – {engagement.titre}, "
                                    f"entité auditée : {entity}, du "
                                    f"{engagement.date_debut:%d/%m/%Y} au "
                                    f"{engagement.date_fin:%d/%m/%Y}."})  # fmt: skip
            blocks += [{"titre": "Objectifs", "niveau": 2},
                       {"texte": engagement.objectifs or "—"},
                       {"titre": "Périmètre", "niveau": 2},
                       {"texte": engagement.perimetre or "—"}]  # fmt: skip
        elif code == "constats":
            if not findings:
                blocks.append({"texte": "Aucun constat validé."})
            for f in findings:
                blocks.append({"titre": f"{f.reference} – {f.titre}", "niveau": 2})
                blocks.append({"texte": f"Criticité : {CRITICITE.get(f.criticite, f.criticite)}"})
                for label, text in (("Critère", f.critere), ("Constat", f.constat),
                                    ("Cause", f.cause), ("Conséquence", f.consequence),
                                    ("Recommandation", f.recommandation)):  # fmt: skip
                    if text:
                        blocks += [{"titre": label, "niveau": 3}, {"texte": text}]
                blocks.append({"titre": "Réponse de l'audité", "niveau": 3})
                position = POSITION.get(f.reponse_position or "", "—")
                answer = f"{position}" + (
                    f" : {f.reponse_commentaire}" if f.reponse_commentaire else ""
                )
                blocks.append({"texte": answer})
                if plans[f.id]:
                    rows = [plan_row(f, p) for p in plans[f.id]]
                    blocks.append({"tableau": [PLAN_HEADER, *rows], "entete": True})
        elif code == "plans_action":
            rows = [plan_row(f, p) for f in findings for p in plans[f.id]]
            if rows:
                blocks.append({"tableau": [PLAN_HEADER, *rows], "entete": True})
            else:
                blocks.append({"texte": "Aucun plan d'action."})
        elif code == "annexes":
            blocks.append({"titre": "Équipe", "niveau": 2})
            blocks.append({"liste": [f"{m.user.nom} – {ROLE.get(m.role_mission, m.role_mission)}"
                                     for m in engagement.members]})  # fmt: skip
            papers = db.scalars(
                select(Workpaper)
                .where(Workpaper.engagement_id == engagement.id, Workpaper.deleted_at.is_(None))
                .order_by(Workpaper.reference)
            ).all()
            blocks.append({"titre": "Papiers de travail", "niveau": 2})
            blocks.append({"liste": [f"{w.reference} – {w.titre}" for w in papers] or ["—"]})
    title = ""  # la page de garde porte le titre
    return title, blocks, template.pied_de_page
