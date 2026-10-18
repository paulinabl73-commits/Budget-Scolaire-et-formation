"""Affectation des comptes aux postes des états financiers (REV-08 à REV-10).

L'affectation automatique retient la racine la plus longue du référentiel qui couvre le
compte ; à longueur égale, une racine assortie d'une règle de sens (REV-09) ne s'applique que
si le solde du compte est dans ce sens (débiteur ou créditeur). Le sens est apprécié pour
chaque exercice : un compte bancaire débiteur en N et créditeur en N-1 figure en trésorerie
actif en N et en trésorerie passif en N-1. Une affectation manuelle prime (REV-08).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.revision import (
    AccountMapping,
    Adjustment,
    AdjustmentLine,
    AuditFile,
    StatementLine,
)
from app.revision.balances import AMOUNTS, BalanceLine
from app.revision.formula import PREVIOUS, evaluate, references
from app.revision.imports import active_balance, balance_lines

ZERO = Decimal(0)
PERIODS = ("N", "N-1")


@dataclass(frozen=True)
class Rule:
    racine: str
    sens: str | None
    poste: str


@dataclass
class Assignment:
    compte: str
    libelle: str | None
    soldes: dict[str, Decimal] = field(default_factory=dict)  # période → solde net (D − C)
    postes: dict[str, str | None] = field(default_factory=dict)  # période → code du poste
    racines: dict[str, str | None] = field(default_factory=dict)
    origine: str = "auto"
    mapping: AccountMapping | None = None


def postes(db: Session, framework_id: uuid.UUID) -> list[StatementLine]:
    return list(
        db.scalars(
            select(StatementLine)
            .where(StatementLine.framework_id == framework_id)
            .order_by(StatementLine.etat, StatementLine.ordre)
        )
    )


def rules(lines: list[StatementLine]) -> list[Rule]:
    out = [Rule(r["racine"], r.get("sens"), ln.code) for ln in lines for r in ln.racines]
    return sorted(out, key=lambda r: -len(r.racine))


def sense(net: Decimal) -> str:
    return "credit" if net < 0 else "debit"


def auto_poste(compte: str, net: Decimal, all_rules: list[Rule]) -> Rule | None:
    """Racine la plus longue couvrant le compte, compatible avec le sens de son solde."""
    wanted = sense(net)
    for rule in all_rules:  # triées par longueur décroissante
        if compte.startswith(rule.racine) and rule.sens in (None, wanted):
            return rule
    return None


def overrides(db: Session, file_id: uuid.UUID) -> dict[str, AccountMapping]:
    rows = db.scalars(
        select(AccountMapping).where(
            AccountMapping.audit_file_id == file_id, AccountMapping.deleted_at.is_(None)
        )
    )
    return {m.compte: m for m in rows}


def _significant(line: BalanceLine) -> bool:
    return any(line.amounts[k] for k in AMOUNTS)


IFRS = "retraitement_ifrs"


def adjustment_nets(
    db: Session, file_id: uuid.UUID, statuses: tuple[str, ...] = ("acceptee",), ifrs: bool = False
) -> dict[str, Decimal]:
    """Effet net (débit − crédit) par compte des écritures d'ajustement retenues (REV-21) ou,
    avec `ifrs`, des retraitements IFRS validés (IFR-01)."""
    rows = db.execute(
        select(AdjustmentLine.compte, AdjustmentLine.debit - AdjustmentLine.credit)
        .join(Adjustment, Adjustment.id == AdjustmentLine.adjustment_id)
        .where(
            Adjustment.audit_file_id == file_id,
            Adjustment.deleted_at.is_(None),
            Adjustment.statut.in_(statuses),
            (Adjustment.type == IFRS) if ifrs else (Adjustment.type != IFRS),
        )
    )
    out: dict[str, Decimal] = defaultdict(Decimal)
    for compte, net in rows:
        out[compte] += net
    return out


def assignments(
    db: Session, file: AuditFile, adjusted: bool = False, ifrs: bool = False
) -> list[Assignment]:
    """Affectation de chaque compte mouvementé des balances N et N-1 actives ; avec
    `adjusted`, le solde N inclut les écritures d'ajustement acceptées (solde révisé) ; avec
    `ifrs`, il inclut en plus les retraitements IFRS validés (IFR-01)."""
    all_rules = rules(postes(db, file.framework_id))
    manual = overrides(db, file.id)
    excluded = get_settings().classes_hors_etats
    accounts: dict[str, Assignment] = {}
    for periode in PERIODS:
        for ln in balance_lines(db, active_balance(db, file.id, periode)):
            if not _significant(ln) or ln.compte[0] in excluded:
                continue
            item = accounts.setdefault(ln.compte, Assignment(ln.compte, ln.libelle))
            item.soldes[periode] = item.soldes.get(periode, ZERO) + ln.net("solde")
    layers = ([False] if adjusted else []) + ([True] if ifrs else [])
    for layer in layers if accounts else []:
        for compte, net in adjustment_nets(db, file.id, ifrs=layer).items():
            item = accounts.setdefault(compte, Assignment(compte, None))
            item.soldes["N"] = item.soldes.get("N", ZERO) + net
    for item in accounts.values():
        m = manual.get(item.compte)
        for periode, net in item.soldes.items():
            if m is not None:
                item.origine, item.mapping = "manuel", m
                credit = net < 0 and m.poste_crediteur
                item.postes[periode] = m.poste_crediteur if credit else m.poste
                item.racines[periode] = None
            else:
                rule = auto_poste(item.compte, net, all_rules)
                item.postes[periode] = rule.poste if rule else None
                item.racines[periode] = rule.racine if rule else None
    return sorted(accounts.values(), key=lambda a: a.compte)


def unmapped(items: list[Assignment]) -> list[Assignment]:
    return [a for a in items if any(p is None for p in a.postes.values())]


# --- États (aperçu) ------------------------------------------------------------------------------


def statement_values(
    lines: list[StatementLine],
    items: list[Assignment],
    periode: str,
    previous: dict[str, Decimal] | None = None,
) -> dict[str, Decimal]:
    """Montant de chaque poste : comptes affectés (signe selon la nature) puis formules ; un
    code suffixé « _N1 » renvoie au montant de l'exercice précédent (`previous`)."""
    by_code = {ln.code: ln for ln in lines}
    raw: dict[str, Decimal] = defaultdict(Decimal)
    for a in items:
        code = a.postes.get(periode)
        if code is not None and code in by_code:
            net = a.soldes[periode]
            raw[code] += net if by_code[code].nature in ("actif", "charge") else -net
    values: dict[str, Decimal] = {}

    def value(code: str, stack: tuple[str, ...] = ()) -> Decimal:
        if code in values:
            return values[code]
        line = by_code.get(code)
        total = raw.get(code, ZERO)
        if line is not None and line.formule and code not in stack:
            deps = {
                r: (previous or {}).get(r.removesuffix(PREVIOUS), ZERO)
                if r.endswith(PREVIOUS)
                else value(r, (*stack, code))
                for r in references(line.formule)
            }
            total += evaluate(line.formule, deps) or ZERO
        values[code] = total
        return total

    for code in by_code:
        value(code)
    return values


class UnmappedError(Exception):
    """Aucun état ne peut être produit : balance N absente ou comptes non affectés (REV-10)."""

    def __init__(self, message: str, comptes: list[str] | None = None) -> None:
        super().__init__(message)
        self.comptes = comptes or []


def file_values(
    db: Session, file: AuditFile, adjusted: bool = False, ifrs: bool = False
) -> dict[str, dict[str, Decimal]]:
    """Montants des postes N et N-1 du dossier (N révisé avec `adjusted`) ; UnmappedError si
    un état ne peut être produit."""
    items = assignments(db, file, adjusted, ifrs)
    if not any("N" in a.soldes for a in items):
        raise UnmappedError("Aucune balance N acceptée")
    missing = unmapped(items)
    if missing:
        raise UnmappedError(
            f"{len(missing)} compte(s) non affecté(s) : aucun état ne peut être produit",
            [a.compte for a in missing],
        )
    lines = postes(db, file.framework_id)
    before = statement_values(lines, items, "N-1")
    return {"N": statement_values(lines, items, "N", before), "N-1": before}
