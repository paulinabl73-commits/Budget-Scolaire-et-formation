"""Risques, contrôles et procédures : bibliothèque (AUD-10) et matrice de mission (AUD-11)."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Boolean, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TrackedMixin
from app.models.user import User


class Cycle(StrEnum):
    ACHATS = "achats"
    VENTES = "ventes"
    PAIE = "paie"
    TRESORERIE = "tresorerie"
    IMMOBILISATIONS = "immobilisations"
    STOCKS = "stocks"
    NOTES_DE_FRAIS = "notes_de_frais"
    SYSTEMES_INFORMATION = "systemes_information"
    GOUVERNANCE = "gouvernance"
    CONFORMITE = "conformite"
    AUTRE = "autre"


class RiskCategory(StrEnum):
    """Catégories d'objectifs du référentiel COSO."""

    OPERATIONNEL = "operationnel"
    REPORTING = "reporting"
    CONFORMITE = "conformite"
    STRATEGIQUE = "strategique"
    FRAUDE = "fraude"


class ControlType(StrEnum):
    PREVENTIF = "preventif"
    DETECTIF = "detectif"


class ControlNature(StrEnum):
    MANUEL = "manuel"
    AUTOMATIQUE = "automatique"
    SEMI_AUTOMATIQUE = "semi_automatique"


class Frequency(StrEnum):
    PONCTUEL = "ponctuel"
    QUOTIDIEN = "quotidien"
    HEBDOMADAIRE = "hebdomadaire"
    MENSUEL = "mensuel"
    TRIMESTRIEL = "trimestriel"
    ANNUEL = "annuel"


class Risk(TrackedMixin, Base):
    """Risque de la bibliothèque (engagement_id vide) ou copie propre à une mission."""

    __tablename__ = "risks"

    libelle: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cycle: Mapped[str] = mapped_column(String(30))
    categorie: Mapped[str] = mapped_column(String(30))
    bibliotheque: Mapped[bool] = mapped_column(Boolean, default=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("engagements.id"), nullable=True, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("risks.id"), nullable=True)


class Control(TrackedMixin, Base):
    __tablename__ = "controls"

    libelle: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cycle: Mapped[str] = mapped_column(String(30))
    type_controle: Mapped[str] = mapped_column(String(20))
    nature: Mapped[str] = mapped_column(String(20))
    frequence: Mapped[str] = mapped_column(String(20))
    bibliotheque: Mapped[bool] = mapped_column(Boolean, default=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("engagements.id"), nullable=True, index=True
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("controls.id"), nullable=True)


class RiskControl(TrackedMixin, Base):
    """Lien risque ↔ contrôle, dans la bibliothèque comme dans une mission."""

    __tablename__ = "risk_controls"

    risk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risks.id"), index=True)
    control_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("controls.id"), index=True)


class TestType(StrEnum):
    """Nature de la procédure (normes IIA 2320 / ISA 330)."""

    CONCEPTION = "conception"  # revue de conception, walk-through
    EFFICACITE = "efficacite"  # test de fonctionnement du contrôle
    SUBSTANTIF = "substantif"  # contrôle de détail ou analytique


class ProcedureStatus(StrEnum):
    A_FAIRE = "a_faire"
    EN_COURS = "en_cours"
    TERMINEE = "terminee"


class Procedure(TrackedMixin, Base):
    """Procédure de test rattachée à un contrôle (AUD-11) ; type dans la bibliothèque."""

    __tablename__ = "procedures"

    control_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("controls.id"), index=True)
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("engagements.id"), nullable=True, index=True
    )
    reference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    type_test: Mapped[str] = mapped_column(String(20))
    bibliotheque: Mapped[bool] = mapped_column(Boolean, default=True)
    # AUD-12 : affectation à un membre de l'équipe avec une échéance.
    assigne_a: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    echeance: Mapped[date | None] = mapped_column(Date, nullable=True)
    statut: Mapped[str] = mapped_column(String(20), default=ProcedureStatus.A_FAIRE.value)

    assignee: Mapped[User | None] = relationship(foreign_keys=[assigne_a], viewonly=True)

    @property
    def en_retard(self) -> bool:
        return (
            self.echeance is not None
            and self.statut != ProcedureStatus.TERMINEE
            and self.echeance < date.today()
        )

    @property
    def assigne_nom(self) -> str | None:
        return self.assignee.nom if self.assignee else None
