"""Rapport de mission (Module 4, REP-01 à REP-03)."""

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TrackedMixin

# Sections possibles d'un rapport de mission, dans l'ordre proposé par défaut.
REPORT_SECTIONS = ("synthese", "contexte", "constats", "plans_action", "annexes")
FINDING_ORDERS = ("criticite_decroissante", "criticite_croissante", "reference")


class MissionReportTemplate(TrackedMixin, Base):
    """Modèle de rapport (REP-01) : logo, page de garde, sections et leur ordre, ordre des
    constats. Un seul modèle par défaut ; un rapport garde le modèle choisi à sa création."""

    __tablename__ = "mission_report_templates"

    nom: Mapped[str] = mapped_column(String(200))
    par_defaut: Mapped[bool] = mapped_column(Boolean, default=False)
    # {"titre", "sous_titre", "mention", "organisation"} ; variables {mission}, {reference},
    # {entite}, {date}.
    page_garde: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # [{"code": REPORT_SECTIONS, "titre": str, "actif": bool}] dans l'ordre du rapport.
    sections: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    ordre_constats: Mapped[str] = mapped_column(String(30), default="criticite_decroissante")
    logo_storage_key: Mapped[str | None] = mapped_column(String(300), nullable=True)
    logo_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    pied_de_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    actif: Mapped[bool] = mapped_column(Boolean, default=True)
    logo_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class MissionReport(TrackedMixin, Base):
    """Rapport d'une mission (REP-02) : modèle choisi et synthèse rédigée par l'équipe ; le
    contenu (constats, réponses, plans d'action) est lu dans la mission à la génération."""

    __tablename__ = "mission_reports"

    engagement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("engagements.id"), unique=True, index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("mission_report_templates.id"))
    synthese: Mapped[str | None] = mapped_column(Text, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
