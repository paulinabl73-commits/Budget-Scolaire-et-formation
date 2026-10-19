"""Rapport au comité d'audit (REP-07) : synthèse trimestrielle exportée en PDF.

Contenu, selon les attentes usuelles d'un comité d'audit (norme IIA 2060, communication à la
direction générale et au conseil) : faits marquants du trimestre, avancement du plan annuel à
la fin du trimestre, missions clôturées et rapports diffusés, constats validés dans le
trimestre (répartition et constats critiques ou élevés), suivi des recommandations (taux de
mise en œuvre, retards par direction) et consommation des ressources.
"""

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.finding import CRITICALITY_ORDER, Finding, FindingStatus
from app.models.report import MissionReport
from app.models.user import User
from app.reporting.dashboards import Filters, direction, missions, recommendations
from app.reporting.mission_report import CRITICITE

MONTHS = {1: 1, 2: 4, 3: 7, 4: 10}


def bounds(annee: int, trimestre: int) -> tuple[dt.date, dt.date]:
    start = dt.date(annee, MONTHS[trimestre], 1)
    end_month = MONTHS[trimestre] + 3
    end = (
        dt.date(annee + 1, 1, 1) if end_month > 12 else dt.date(annee, end_month, 1)
    ) - dt.timedelta(days=1)
    return start, end


def _in(value: dt.datetime | None, start: dt.date, end: dt.date) -> bool:
    return value is not None and start <= value.date() <= end


def build(
    db: Session, user: User, annee: int, trimestre: int, organisation: str
) -> tuple[str, list[dict[str, Any]]]:
    start, end = bounds(annee, trimestre)
    label = f"T{trimestre} {annee}"
    plan = direction(db, user, Filters(dt.date(annee, 1, 1), end))
    scope = list(db.scalars(missions(db, user, Filters())))
    ids = [e.id for e in scope]
    closed = [e for e in scope if _in(e.cloturee_le, start, end)]
    reports = (
        {
            r.engagement_id: r
            for r in db.scalars(
                select(MissionReport).where(
                    MissionReport.engagement_id.in_(ids), MissionReport.deleted_at.is_(None)
                )
            )
        }
        if ids
        else {}
    )
    diffused = [e for e in scope if e.id in reports and _in(reports[e.id].diffuse_le, start, end)]
    validated = (
        [
            f
            for f in db.scalars(
                select(Finding).where(
                    Finding.engagement_id.in_(ids),
                    Finding.deleted_at.is_(None),
                    Finding.statut == FindingStatus.VALIDE.value,
                )
            )
            if _in(f.valide_le, start, end)
        ]
        if ids
        else []
    )
    by_ref = {e.id: e for e in scope}
    reco = recommendations(db, user, Filters())
    levels = [c.value for c in reversed(CRITICALITY_ORDER)]
    blocks: list[dict[str, Any]] = [
        {"garde": organisation, "taille": 12},
        {"garde": "Rapport au comité d'audit", "taille": 24},
        {
            "garde": f"Synthèse du trimestre {label} ({start:%d/%m/%Y} – {end:%d/%m/%Y})",
            "taille": 14,
        },
        {"garde": f"Établi le {dt.date.today():%d/%m/%Y}", "taille": 10},
        {"saut": True},
        {"titre": "1. Faits marquants", "niveau": 1},
        {
            "liste": [
                f"{len(closed)} mission(s) clôturée(s) et {len(diffused)} rapport(s) "
                "diffusé(s) sur le trimestre.",
                f"{len(validated)} constat(s) validé(s), dont "
                f"{sum(f.criticite in ('critique', 'elevee') for f in validated)} "
                "de criticité élevée ou critique.",
                f"Taux de mise en œuvre des recommandations : {reco['taux_mise_en_oeuvre']} % "
                f"({reco['taux_mise_en_oeuvre_echus']} % des plans échus).",
                f"{len(reco['plans_en_retard'])} plan(s) d'action en retard.",
            ]
        },
        {"titre": f"2. Avancement du plan annuel {annee}", "niveau": 1},
    ]
    if plan["plan"]:
        p = plan["plan"]
        blocks.append(
            {
                "tableau": [
                    ["Missions prévues", "Lancées", "Clôturées", "Taux de réalisation"],
                    [
                        str(p["missions_prevues"]),
                        str(p["missions_lancees"]),
                        str(p["missions_cloturees"]),
                        f"{p['taux_realisation']} %",
                    ],
                ]
            }
        )
    else:
        blocks.append({"texte": "Aucun plan annuel validé pour l'année."})
    blocks += [
        {"titre": "3. Missions clôturées et rapports diffusés", "niveau": 1},
        {
            "tableau": [["Mission", "Entité", "Clôture", "Rapport diffusé"]]
            + [
                [
                    f"{e.reference} – {e.titre}",
                    e.entity.nom if e.entity else "—",
                    e.cloturee_le.strftime("%d/%m/%Y") if e.cloturee_le else "—",
                    reports[e.id].diffuse_le.strftime("%d/%m/%Y")
                    if e.id in reports and reports[e.id].diffuse_le
                    else "—",
                ]
                for e in sorted({*closed, *diffused}, key=lambda x: x.reference)
            ]
        }
        if closed or diffused
        else {"texte": "Aucune mission clôturée sur le trimestre."},
        {"titre": "4. Constats validés sur le trimestre", "niveau": 1},
        {
            "tableau": [["Criticité", "Constats"]]
            + [[CRITICITE[c], str(sum(f.criticite == c for f in validated))] for c in levels]
        },
    ]
    major = [f for f in validated if f.criticite in ("critique", "elevee")]
    if major:
        blocks.append({"titre": "Constats critiques et élevés", "niveau": 2})
        blocks.append(
            {
                "tableau": [["Mission", "Constat", "Criticité"]]
                + [
                    [
                        by_ref[f.engagement_id].reference,
                        f"{f.reference} – {f.titre}",
                        CRITICITE[f.criticite],
                    ]
                    for f in sorted(major, key=lambda f: (levels.index(f.criticite), f.reference))
                ]
            }
        )
    blocks += [
        {"titre": "5. Suivi des recommandations", "niveau": 1},
        {
            "texte": f"Taux de mise en œuvre : {reco['taux_mise_en_oeuvre']} % ; "
            f"plans échus mis en œuvre : {reco['taux_mise_en_oeuvre_echus']} %."
        },
    ]
    if reco["retards_par_direction"]:
        blocks.append(
            {
                "tableau": [["Direction", "Plans en retard", "Plus ancienne échéance"]]
                + [
                    [
                        r["direction"],
                        str(r["plans_en_retard"]),
                        dt.date.fromisoformat(r["plus_ancienne_echeance"]).strftime("%d/%m/%Y"),
                    ]
                    for r in reco["retards_par_direction"]
                ]
            }
        )
        blocks.append({"titre": "Retards les plus anciens", "niveau": 2})
        blocks.append(
            {
                "tableau": [["Constat", "Plan d'action", "Responsable", "Retard (jours)"]]
                + [
                    [
                        f"{p['mission']} · {p['constat']}",
                        p["description"],
                        p["responsable"] or "—",
                        str(p["jours_de_retard"]),
                    ]
                    for p in reco["plans_en_retard"][:10]
                ]
            }
        )
    else:
        blocks.append({"texte": "Aucun plan d'action en retard."})
    blocks += [
        {"titre": "6. Ressources", "niveau": 1},
        {
            "texte": f"Depuis le début de l'exercice : {plan['jours_consommes']} jour(s) "
            f"consommé(s) pour un budget de {plan['budget_jours']} jour(s) sur les missions "
            f"de la période ({plan['taux_consommation']} %)."
        },
    ]
    return f"Rapport au comité d'audit – {label}", blocks
