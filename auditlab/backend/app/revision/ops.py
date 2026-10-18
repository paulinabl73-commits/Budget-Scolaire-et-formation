"""Contrôles des organismes de prévoyance sociale lancés depuis un dossier CIPRES (CIP-02 à
CIP-05) : chaque contrôle est une opération du Module 2 dont les valeurs réglementaires sont
lues dans le référentiel du dossier (CIP-09), pour son pays et son exercice."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.revision import AccountingFramework, AuditFile
from app.revision.parameters import resolve


class Context:
    """Lecture des paramètres du dossier ; note les manquants et les valeurs retenues."""

    def __init__(self, db: Session, file: AuditFile, fw: AccountingFramework) -> None:
        self.db, self.file, self.fw = db, file, fw
        self.missing: list[str] = []
        self.used: list[dict[str, Any]] = []

    @property
    def branches(self) -> list[str]:
        return [b["code"] for b in self.fw.branches]

    def value(self, code: str, branche: str | None = None, required: bool = True) -> str | None:
        p = resolve(self.db, self.fw.id, code, self.file.pays, self.file.exercice, branche)
        if p is None:
            if required:
                self.missing.append(f"{code}{f' ({branche})' if branche else ''}")
            return None
        value = format(p.valeur.normalize(), "f")
        self.used.append(
            {
                "code": code,
                "branche": branche,
                "valeur": value,
                "unite": p.unite,
                "pays": p.pays,
                "exercice": p.exercice,
            }
        )
        return value


@dataclass(frozen=True)
class OpsControl:
    code: str
    exigence: str
    libelle: str
    operation: str
    tables: tuple[str, ...]
    regulatory: Callable[[Context], dict[str, Any]]
    fixed: Callable[[AuditFile], dict[str, Any]] = field(default=lambda f: {})


def _cotisations(ctx: Context) -> dict[str, Any]:
    rates = {b: v for b in ctx.branches if (v := ctx.value("taux_cotisation", b, False))}
    if not rates:
        ctx.missing.append("taux_cotisation")
    # Plafond exigé pour chaque branche cotisée ; 0 = pas de plafond.
    ceilings = {b: ctx.value("plafond_cotisation", b) for b in rates}
    return {"taux": rates, "plafonds": {b: v for b, v in ceilings.items() if v is not None}}


def _recouvrement(ctx: Context) -> dict[str, Any]:
    return {
        "delai_jours": ctx.value("delai_declaration_jours"),
        "taux_majoration": ctx.value("taux_majoration_retard"),
        "par_mois": ctx.value("majoration_par_mois_retard"),
    }


def _creances(ctx: Context) -> dict[str, Any]:
    return {
        "anciennete_mois": ctx.value("anciennete_depreciation_creances_mois"),
        "taux_depreciation": ctx.value("taux_depreciation_creances"),
    }


def _prestations(ctx: Context) -> dict[str, Any]:
    return {
        "age_minimum": ctx.value("age_minimum_pension"),
        "age_maximum": ctx.value("age_maximum_beneficiaire"),
        "validite_certificat_mois": ctx.value("validite_certificat_vie_mois"),
        "montant_minimum": ctx.value("pension_minimum"),
        "montant_maximum": ctx.value("pension_maximum"),
    }


def _exercice(file: AuditFile) -> dict[str, Any]:
    return {"debut": file.date_debut.isoformat(), "fin": file.date_fin.isoformat()}


def _cloture(file: AuditFile) -> dict[str, Any]:
    return {"date_reference": file.date_fin.isoformat()}


CONTROLS: dict[str, OpsControl] = {
    c.code: c
    for c in (
        OpsControl(
            "cotisations",
            "CIP-02",
            "Recalcul des cotisations par employeur",
            "cip_cotisations",
            ("Déclarations nominatives des salaires", "Cotisations émises et encaissées"),
            _cotisations,
        ),
        OpsControl(
            "recouvrement",
            "CIP-03",
            "Recouvrement : déclarations manquantes ou tardives, majorations",
            "cip_recouvrement",
            ("Déclarations des employeurs", "Registre des employeurs"),
            _recouvrement,
            _exercice,
        ),
        OpsControl(
            "creances",
            "CIP-03",
            "Créances anciennes sur cotisants non dépréciées",
            "cip_creances",
            ("Créances sur cotisants à la clôture",),
            _creances,
            _cloture,
        ),
        OpsControl(
            "prestations",
            "CIP-04",
            "Prestations et pensions : doublons, âges, décès, certificats de vie, barème",
            "cip_prestations",
            ("Fichier des bénéficiaires",),
            _prestations,
            _cloture,
        ),
    )
}
