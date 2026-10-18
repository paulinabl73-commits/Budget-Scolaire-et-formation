"""Indicateurs des organismes de prévoyance sociale tirés des soldes révisés (CIP-06, CIP-07).

Les agrégats sont des postes du référentiel CIPRES désignés par un code réservé, à prévoir dans
les états importés (poste de détail ou formule) :
- COT cotisations émises, CCO créances sur cotisants, FGE frais de gestion (CIP-06) ;
- RTE réserves techniques, PRE prestations servies, PPL produits des placements, PLA_<catégorie>
  placements d'une catégorie (CIP-07).
Cotisations encaissées = cotisations émises + créances sur cotisants N-1 − créances N.
Les plafonds et limites sont des paramètres réglementaires (CIP-09).
"""

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.revision import AccountingFramework, AuditFile
from app.revision.mapping import assignments, postes, statement_values, unmapped
from app.revision.ops import Context

ZERO = Decimal(0)
HUNDRED = Decimal(100)
FEES = ("COT", "CCO", "FGE")


class NotMapped(LookupError):
    pass


def _pct(num: Decimal, den: Decimal) -> Decimal | None:
    return (num / den * HUNDRED).quantize(Decimal("0.01")) if den else None


def file_values(db: Session, file: AuditFile) -> dict[str, dict[str, Decimal]]:
    """Montant de chaque poste en N et N-1 (soldes N révisés) ; NotMapped sans balance N ou si
    un compte n'est pas affecté (REV-10)."""
    items = assignments(db, file, adjusted=True)
    if not any("N" in a.soldes for a in items):
        raise NotMapped("Balance N absente : les indicateurs ne peuvent être calculés")
    if unmapped(items):
        raise NotMapped("Comptes non affectés : les indicateurs ne peuvent être calculés")
    lines = postes(db, file.framework_id)
    n1 = statement_values(lines, items, "N-1")
    return {"N": statement_values(lines, items, "N", n1), "N-1": n1}


def _codes(db: Session, file: AuditFile) -> set[str]:
    return {ln.code for ln in postes(db, file.framework_id)}


def management_fees(
    db: Session, file: AuditFile, ctx: Context, values: dict[str, dict[str, Decimal]]
) -> dict[str, Any]:
    """CIP-06 : frais de gestion / cotisations encaissées, par exercice (N, puis le N du dossier
    précédent lorsqu'il existe), comparé au plafond des règles communes de gestion."""
    missing = [c for c in FEES if c not in _codes(db, file)]
    if missing:
        return {"postes_manquants": missing, "exercices": []}
    ceiling = ctx.value("plafond_frais_gestion")
    years = []
    current: AuditFile | None = file
    while current is not None and len(years) < 2:
        try:
            v = values if current is file else file_values(db, current)
        except NotMapped:
            break  # dossier précédent incomplet : exercice non présenté
        cashed = v["N"]["COT"] + v["N-1"]["CCO"] - v["N"]["CCO"]
        ratio = _pct(v["N"]["FGE"], cashed)
        years.append(
            {
                "exercice": current.exercice,
                "frais_gestion": str(v["N"]["FGE"]),
                "cotisations_emises": str(v["N"]["COT"]),
                "variation_creances": str(v["N"]["CCO"] - v["N-1"]["CCO"]),
                "cotisations_encaissees": str(cashed),
                "ratio": str(ratio) if ratio is not None else None,
                "plafond": ceiling,
                "conforme": None if ratio is None or ceiling is None else ratio <= Decimal(ceiling),
            }
        )
        current = db.get(AuditFile, current.precedent_id) if current.precedent_id else None
    return {"postes_manquants": [], "exercices": years}


def indicators(db: Session, file: AuditFile) -> dict[str, Any]:
    fw = db.get(AccountingFramework, file.framework_id)
    ctx = Context(db, file, fw)
    values = file_values(db, file)
    out = {"frais_gestion": management_fees(db, file, ctx, values)}
    return {**out, "parametres": ctx.used, "parametres_manquants": ctx.missing}
