"""Contrôles d'intégrité bloquants à l'import (REV-06).

Toute anomalie rejette l'import : la balance reste consultable dans l'historique mais n'est
jamais utilisée. Les contrôles qui dépendent d'une autre donnée (balance N-1, grand livre)
s'exécutent à l'import de la seconde, quel que soit l'ordre ; tant que celle-ci manque, un
avertissement le signale.
"""

from collections import defaultdict
from decimal import Decimal
from typing import Any

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.revision import FrameworkAccount
from app.revision.balances import BalanceLine
from app.revision.imports import CONTROLS, Parsed, active_balance, balance_lines

MAX_DETAILS = 50  # anomalies détaillées par contrôle ; au-delà, une ligne de synthèse
ZERO = Decimal(0)


def _tolerance(parsed: Parsed) -> Decimal:
    return Decimal(str(get_settings().tolerance_controles_import)) + parsed.tolerance


def _fmt(amount: Any) -> str:
    return f"{Decimal(amount):,.2f}".replace(",", " ").replace(".", ",").removesuffix(",00")


def _report(parsed: Parsed, code: str, items: list[tuple[str | None, str]]) -> None:
    """Ajoute les anomalies (compte, message) d'un contrôle, au plus MAX_DETAILS en détail."""
    for compte, message in items[:MAX_DETAILS]:
        entry = {"code": code, "message": message}
        if compte:
            entry["compte"] = compte
        parsed.anomalies.append(entry)
    if len(items) > MAX_DETAILS:
        rest = len(items) - MAX_DETAILS
        parsed.anomalies.append({"code": code, "message": f"… et {rest} autre(s) écart(s)"})


def _warn(parsed: Parsed, code: str, message: str) -> None:
    parsed.avertissements.append({"code": code, "message": message})


def _nets(lines: list[BalanceLine], prefix: str) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(Decimal)
    for ln in lines:
        out[ln.compte] += ln.net(prefix)
    return out


def _gaps(a: dict[str, Decimal], b: dict[str, Decimal], tol: Decimal, keep=None) -> list[str]:
    accounts = (c for c in set(a) | set(b) if keep is None or keep(c))
    return sorted(c for c in accounts if abs(a.get(c, ZERO) - b.get(c, ZERO)) > tol)


# --- Balance équilibrée et cohérente ligne à ligne ----------------------------------------------


def equilibre(db: Session, parsed: Parsed) -> None:
    tol = _tolerance(parsed)
    if parsed.ledger is not None:
        debit, credit = parsed.ledger["debit"].sum(), parsed.ledger["credit"].sum()
        if abs(Decimal(debit) - Decimal(credit)) > tol:
            message = f"Grand livre déséquilibré : débits {_fmt(debit)} ≠ crédits {_fmt(credit)}"
            _report(parsed, "desequilibre", [(None, message)])
        return
    if parsed.request.type != "balance":
        return
    labels = {"ouverture": "à-nouveaux", "mouvement": "mouvements", "solde": "soldes"}
    for prefix, label in labels.items():
        d = sum((ln.amounts[f"{prefix}_debit"] for ln in parsed.lines), ZERO)
        c = sum((ln.amounts[f"{prefix}_credit"] for ln in parsed.lines), ZERO)
        if abs(d - c) > tol:
            message = (
                f"Balance déséquilibrée sur les {label} : débits {_fmt(d)} ≠ crédits {_fmt(c)} "
                f"(écart {_fmt(d - c)})"
            )
            _report(parsed, "desequilibre", [(None, message)])
    incoherent = []
    for ln in parsed.lines:
        o, m, s = ln.net("ouverture"), ln.net("mouvement"), ln.net("solde")
        if abs(o + m - s) > tol:
            message = (
                f"Compte {ln.compte} : à-nouveaux {_fmt(o)} + mouvements {_fmt(m)} "
                f"≠ solde {_fmt(s)}"
            )
            incoherent.append((ln.compte, message))
    _report(parsed, "ligne_incoherente", incoherent)


# --- Comptes hors plan -------------------------------------------------------------------------


def hors_plan(db: Session, parsed: Parsed) -> None:
    """Chaque compte doit commencer par une racine du référentiel d'au moins N chiffres."""
    if parsed.request.type not in ("balance", "grand_livre"):
        return  # les balances auxiliaires portent des codes tiers
    minimum = get_settings().racine_minimale_plan
    numbers = db.scalars(
        select(FrameworkAccount.numero).where(
            FrameworkAccount.framework_id == parsed.file.framework_id
        )
    )
    roots = {n for n in numbers if len(n) >= minimum}
    if parsed.ledger is not None:
        accounts = sorted(set(parsed.ledger["compte"].to_list()))
    else:
        accounts = sorted({ln.compte for ln in parsed.lines})
    unknown = [a for a in accounts if not any(a.startswith(r) for r in roots)]
    message = "Compte {} hors plan : aucune racine du référentiel ne le couvre"
    _report(parsed, "hors_plan", [(a, message.format(a)) for a in unknown])


# --- À-nouveaux N = soldes de clôture N-1 ------------------------------------------------------


def a_nouveaux(db: Session, parsed: Parsed) -> None:
    req = parsed.request
    if req.type != "balance":
        return
    other = active_balance(db, parsed.file.id, "N-1" if req.periode == "N" else "N")
    if req.periode == "N":
        opening, closing = parsed.lines, balance_lines(db, other)
    else:
        opening, closing = balance_lines(db, other), parsed.lines
    if not opening or not closing:
        missing = "N-1" if req.periode == "N" else "N"
        message = f"Balance {missing} absente : les à-nouveaux seront contrôlés à son import"
        _warn(parsed, "a_nouveaux_differes", message)
        return
    settings = get_settings()
    tol = _tolerance(parsed)
    ouv, clo = _nets(opening, "ouverture"), _nets(closing, "solde")
    # Comptes de bilan hors capitaux propres : égalité compte par compte.
    detail_classes = settings.classes_bilan.replace("1", "")
    gaps = _gaps(ouv, clo, tol, keep=lambda c: c[0] in detail_classes)
    message = "Compte {} : à-nouveau N {} ≠ solde de clôture N-1 {}"
    _report(parsed, "a_nouveaux", [
        (c, message.format(c, _fmt(ouv.get(c, ZERO)), _fmt(clo.get(c, ZERO)))) for c in gaps
    ])  # fmt: skip
    # Capitaux propres : le résultat N-1 a pu être affecté entre comptes de la classe 1 ;
    # le contrôle porte sur le total (classe 1 et résultat N-1 des classes de gestion).
    equity_n = sum((v for c, v in ouv.items() if c[0] == "1"), ZERO)
    closing_classes = "1" + settings.classes_resultat
    equity_n1 = sum((v for c, v in clo.items() if c[0] in closing_classes), ZERO)
    if abs(equity_n - equity_n1) > tol:
        message = (
            f"Capitaux propres : à-nouveaux N {_fmt(equity_n)} ≠ classe 1 et résultat "
            f"de clôture N-1 {_fmt(equity_n1)}"
        )
        _report(parsed, "a_nouveaux", [(None, message)])
    if all(ln.net("ouverture") == 0 for ln in opening) and any(clo.values()):
        message = (
            "La balance N ne comporte aucun à-nouveau : si votre logiciel les intègre aux "
            "mouvements, exportez-la avec les soldes d'ouverture"
        )
        _warn(parsed, "a_nouveaux_absents", message)


# --- Grand livre cohérent avec la balance compte par compte -------------------------------------


def _ledger_nets(ledger: pl.DataFrame, opening_journals: tuple[str, ...]) -> dict[str, Decimal]:
    df = ledger
    if "journal" in df.columns:
        journals = [j.upper() for j in opening_journals]
        df = df.filter(~pl.col("journal").fill_null("").str.to_uppercase().is_in(journals))
    net = (pl.col("debit").sum() - pl.col("credit").sum()).alias("net")
    grouped = df.group_by("compte").agg(net)
    return {r["compte"]: Decimal(r["net"]) for r in grouped.iter_rows(named=True)}


def grand_livre(db: Session, parsed: Parsed) -> None:
    from app.analytics.store import data_dir
    from app.models.data import Dataset

    req = parsed.request
    if req.type == "grand_livre":
        lines = balance_lines(db, active_balance(db, parsed.file.id, "N"))
        ledger = parsed.ledger
        if not lines:
            message = "Balance N absente : la concordance sera contrôlée à son import"
            _warn(parsed, "grand_livre_differe", message)
            return
    elif req.type == "balance" and req.periode == "N":
        gl = active_balance(db, parsed.file.id, "N", "grand_livre")
        if gl is None or gl.dataset_id is None:
            return
        ledger = pl.read_parquet(data_dir() / db.get(Dataset, gl.dataset_id).chemin_parquet)
        lines = parsed.lines
    else:
        return
    gl_nets = _ledger_nets(ledger, req.journaux_a_nouveaux)
    bal_nets = _nets(lines, "mouvement")
    message = "Compte {} : mouvements du grand livre {} ≠ mouvements de la balance {}"
    _report(parsed, "grand_livre", [
        (c, message.format(c, _fmt(gl_nets.get(c, ZERO)), _fmt(bal_nets.get(c, ZERO))))
        for c in _gaps(gl_nets, bal_nets, _tolerance(parsed))
    ])  # fmt: skip


# --- Balance auxiliaire = compte collectif -----------------------------------------------------


def auxiliaire(db: Session, parsed: Parsed) -> None:
    req = parsed.request
    if not req.type.startswith("aux_"):
        return
    general = balance_lines(db, active_balance(db, parsed.file.id, req.periode))
    if not general:
        message = (
            f"Balance générale {req.periode} absente : rapprochement avec le compte collectif "
            "non fait ; réimportez la balance auxiliaire après elle"
        )
        _warn(parsed, "auxiliaire_differe", message)
        return
    root = req.compte_collectif or ""
    aux = sum((ln.net("solde") for ln in parsed.lines), ZERO)
    control = sum((ln.net("solde") for ln in general if ln.compte.startswith(root)), ZERO)
    if abs(aux - control) > _tolerance(parsed):
        message = (
            f"Balance auxiliaire {_fmt(aux)} ≠ solde des comptes {root} "
            f"de la balance générale {_fmt(control)}"
        )
        _report(parsed, "auxiliaire", [(None, message)])


CONTROLS.extend([equilibre, hors_plan, a_nouveaux, grand_livre, auxiliaire])
