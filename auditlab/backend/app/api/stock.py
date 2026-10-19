"""Stocks d'une clôture (RCO-12) : inventaire physique, valorisation, dépréciation et
écriture de variation de stock (inventaire intermittent : les comptes de stock portent le
stock initial jusqu'à l'écriture)."""

import json
import uuid
from collections import defaultdict
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.justifications import _client
from app.cabinet.entries import propose
from app.cabinet.stock import valuation
from app.cabinet.tables import read_table
from app.models.portfolio import Client, StockCount
from app.models.revision import AccountingFramework, AuditFile
from app.revision.balances import clean_account
from app.revision.currency import decimals, quantum
from app.revision.mapping import assignments

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)
ORIGIN = "RCO-12"
INVENTORY = {
    "article": ("reference", "code article", "code"),
    "libelle": ("designation", "intitule"),
    "compte": ("compte de stock",),
    "quantite": ("quantite inventoriee", "qte", "quantité"),
    "cout_unitaire": ("cout", "prix unitaire"),
    "vnr": ("valeur nette de realisation", "prix de vente net"),
}
MOVEMENTS = {
    "article": ("reference", "code article", "code"),
    "date": ("date entree",),
    "type": ("nature",),
    "quantite": ("qte", "quantité"),
    "prix_unitaire": ("cout unitaire", "pu", "prix"),
}


class MethodIn(BaseModel):
    methode: Literal["cmp", "peps"]


@lru_cache
def accounts() -> dict[str, dict[str, dict[str, str]]]:
    path = Path(__file__).parents[1] / "cabinet" / "data" / "stocks.json"
    return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items() if k[0] != "_"}


def _rules(db: Session, file: AuditFile) -> dict[str, dict[str, str]]:
    return accounts().get(db.get(AccountingFramework, file.framework_id).code, {})


def _rule_of(compte: str, rules: dict[str, dict[str, str]]) -> tuple[str, dict[str, str]] | None:
    root = max((r for r in rules if compte.startswith(r)), key=len, default=None)
    return (root, rules[root]) if root else None


def _count(db: Session, file: AuditFile, client: Client, create: bool) -> StockCount | None:
    row = db.scalar(
        select(StockCount).where(
            StockCount.audit_file_id == file.id, StockCount.deleted_at.is_(None)
        )
    )
    if row is None and create:
        row = StockCount(
            client_id=client.id, audit_file_id=file.id, inventaire=[], mouvements=[], fichiers={}
        )
        db.add(row)
        db.flush()
    return row


def build(db: Session, file: AuditFile, count: StockCount | None) -> dict[str, Any]:
    if count is None or not count.inventaire:
        return {
            "methode": count.methode if count else "cmp",
            "articles": [],
            "comptes": [],
            "non_valorises": [],
            "fichiers": count.fichiers if count else {},
        }
    q = quantum(decimals(db, file.devise))
    result = valuation(count.inventaire, count.mouvements, count.methode, q)
    rules = _rules(db, file)
    books = {a.compte: a.soldes.get("N", ZERO) for a in assignments(db, file)}
    final: dict[str, Decimal] = defaultdict(Decimal)
    depreciation: dict[str, Decimal] = defaultdict(Decimal)
    unknown = []
    for r in result["articles"]:
        rule = _rule_of(r["compte"], rules)
        if rule is None:
            unknown.append(r["compte"])
            continue
        final[r["compte"]] += Decimal(r["valeur"])
        depreciation[rule[1]["depreciation"]] += Decimal(r["depreciation"])
    comptes = []
    for compte in sorted(set(final) | {c for c in books if _rule_of(c, rules)}):
        stock = final.get(compte, ZERO)
        book = books.get(compte, ZERO)
        comptes.append(
            {
                "compte": compte,
                "stock_final": str(stock),
                "solde_comptable": str(book),
                "variation": str(stock - book),
            }
        )
    deps = []
    for root, required in sorted(depreciation.items()):
        existing = -sum((v for c, v in books.items() if c.startswith(root)), ZERO)
        deps.append(
            {
                "compte": root,
                "requise": str(required),
                "comptabilisee": str(existing),
                "ecart": str(required - existing),
            }
        )
    return {
        "methode": count.methode,
        **result,
        "comptes": comptes,
        "depreciations": deps,
        "comptes_sans_regle": sorted(set(unknown)),
        "fichiers": count.fichiers,
    }


def _context(db: Session, file_id: uuid.UUID, user: Any, write: bool) -> tuple[AuditFile, Client]:
    file, engagement = get_file(db, file_id, user)
    if write:
        require_work(file, engagement, user)
    return file, _client(db, file)


@router.get("/audit-files/{file_id}/stock")
def read_stock(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, client = _context(db, file_id, user, False)
    return build(db, file, _count(db, file, client, False))


@router.post("/audit-files/{file_id}/stock/files/{kind}", status_code=status.HTTP_201_CREATED)
async def upload_stock(
    file_id: uuid.UUID,
    kind: Literal["inventory", "movements"],
    file: UploadFile,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, Any]:
    """Inventaire physique (article, compte, quantité, coût unitaire et VNR facultatifs) ou
    entrées de l'exercice (article, date, nature « initial » pour le stock d'ouverture,
    quantité, prix unitaire) ; un nouvel import remplace le précédent."""
    audit_file, client = _context(db, file_id, user, True)
    content = await file.read()
    if kind == "inventory":
        rows = read_table(
            content,
            file.filename or "x.csv",
            INVENTORY,
            ("article", "compte", "quantite"),
            amounts=("quantite", "cout_unitaire", "vnr"),
        )
        for r in rows:
            r["compte"] = clean_account(r["compte"])
    else:
        rows = read_table(
            content,
            file.filename or "x.csv",
            MOVEMENTS,
            ("article", "quantite", "prix_unitaire"),
            amounts=("quantite", "prix_unitaire"),
            dates=("date",),
        )
        for r in rows:
            r["type"] = (
                "initial"
                if (r.get("type") or "").lower().startswith(("init", "ouv", "si"))
                else "entree"
            )
    count = _count(db, audit_file, client, True)
    if kind == "inventory":
        count.inventaire = rows
    else:
        count.mouvements = rows
    count.fichiers = {**count.fichiers, kind: {"nom": file.filename, "lignes": len(rows)}}
    db.commit()
    return build(db, audit_file, count)


@router.put("/audit-files/{file_id}/stock/method")
def set_method(
    file_id: uuid.UUID, body: MethodIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, client = _context(db, file_id, user, True)
    count = _count(db, file, client, True)
    count.methode = body.methode
    db.commit()
    return build(db, file, count)


@router.post("/audit-files/{file_id}/stock/entry", status_code=status.HTTP_201_CREATED)
def stock_entry(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Variation de stock (stock final − solde comptable) et ajustement de la dépréciation."""
    file, client = _context(db, file_id, user, True)
    data = build(db, file, _count(db, file, client, False))
    if not data["articles"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "Aucun inventaire valorisé")
    if data["non_valorises"] or data["comptes_sans_regle"]:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Articles non valorisés ou comptes de stock sans règle : "
            + ", ".join(data["non_valorises"] + data["comptes_sans_regle"]),
        )
    rules = _rules(db, file)
    lines = []
    for c in data["comptes"]:
        diff = Decimal(c["variation"])
        variation = _rule_of(c["compte"], rules)[1]["variation"]
        side = ("debit", "credit") if diff > 0 else ("credit", "debit")
        lines += [
            {"compte": c["compte"], "libelle": "Stock final", side[0]: abs(diff)},
            {"compte": variation, "libelle": "Variation de stock", side[1]: abs(diff)},
        ]
    for d in data["depreciations"]:
        gap = Decimal(d["ecart"])
        rule = next(r for r in rules.values() if r["depreciation"] == d["compte"])
        if gap > 0:
            lines += [
                {
                    "compte": rule["dotation"],
                    "libelle": "Dotation dépréciation des stocks",
                    "debit": gap,
                },
                {"compte": d["compte"], "libelle": "Dépréciation des stocks", "credit": gap},
            ]
        elif gap < 0:
            lines += [
                {"compte": d["compte"], "libelle": "Dépréciation des stocks", "debit": -gap},
                {
                    "compte": rule["reprise"],
                    "libelle": "Reprise dépréciation des stocks",
                    "credit": -gap,
                },
            ]
    method = {"cmp": "coût moyen pondéré", "peps": "premier entré, premier sorti"}[data["methode"]]
    return propose(
        db,
        file,
        user,
        ORIGIN,
        f"Variation et dépréciation des stocks {file.exercice}",
        f"Inventaire physique valorisé au {method} (RCO-12) : {len(data['articles'])} article(s).",
        lines,
    )
