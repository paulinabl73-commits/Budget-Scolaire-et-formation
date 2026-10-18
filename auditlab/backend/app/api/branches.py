"""Suivi par branche d'un organisme de prévoyance sociale (CIP-01) : chaque compte et chaque
contrôle est rattaché à une branche ; états et ratios par branche et pour la gestion
administrative."""

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.ratios import _ratio
from app.models.program import Control
from app.models.revision import AccountBranch, AccountingFramework, AuditFile, FrameworkAccount
from app.revision.mapping import PERIODS, assignments, postes, statement_values

router = APIRouter(tags=["OPS – branches"])
ZERO = Decimal(0)


class BranchIn(BaseModel):
    branche: str | None = Field(default=None, max_length=20)


def framework_branches(
    db: Session, file: AuditFile
) -> tuple[AccountingFramework, list[dict[str, str]]]:
    fw = db.get(AccountingFramework, file.framework_id)
    if not fw.branches:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Le référentiel du dossier ne comporte pas de branches"
        )
    return fw, fw.branches


def _manual(db: Session, file_id: uuid.UUID) -> dict[str, AccountBranch]:
    rows = db.scalars(
        select(AccountBranch).where(
            AccountBranch.audit_file_id == file_id, AccountBranch.deleted_at.is_(None)
        )
    )
    return {r.compte: r for r in rows}


def branch_of_accounts(db: Session, file: AuditFile) -> dict[str, tuple[str | None, str]]:
    """Branche de chaque compte du dossier et son origine (manuelle, plan, aucune)."""
    plan = sorted(
        (
            (a.numero, a.branche)
            for a in db.scalars(
                select(FrameworkAccount).where(
                    FrameworkAccount.framework_id == file.framework_id,
                    FrameworkAccount.branche.is_not(None),
                )
            )
        ),
        key=lambda x: -len(x[0]),
    )
    manual = _manual(db, file.id)
    out = {}
    for a in assignments(db, file, adjusted=True):
        if a.compte in manual:
            out[a.compte] = (manual[a.compte].branche, "manuelle")
            continue
        root = next((b for n, b in plan if a.compte.startswith(n)), None)
        out[a.compte] = (root, "plan" if root else "aucune")
    return out


def build(db: Session, file: AuditFile) -> dict[str, Any]:
    fw, branches = framework_branches(db, file)
    items = assignments(db, file, adjusted=True)
    of = branch_of_accounts(db, file)
    lines = postes(db, file.framework_id)
    states: dict[str, Any] = {}
    ratios: dict[str, Any] = {}
    for b in branches:
        mine = [a for a in items if of.get(a.compte, (None,))[0] == b["code"]]
        n1 = statement_values(lines, mine, "N-1")
        values = {"N": statement_values(lines, mine, "N", n1), "N-1": n1}
        states[b["code"]] = [
            {
                "code": ln.code,
                "libelle": ln.libelle,
                "etat": ln.etat,
                "niveau": ln.niveau,
                **{p: str(values[p].get(ln.code, ZERO)) for p in PERIODS},
            }
            for ln in lines
            if ln.etat != "flux_tresorerie"
        ]
        ratios[b["code"]] = [
            {
                "code": r["code"],
                "libelle": r["libelle"],
                "unite": r.get("unite", "ratio"),
                **{p: _ratio(r["formule"], values[p], r.get("unite", "ratio")) for p in PERIODS},
            }
            for r in fw.ratios
        ]
    controls = db.scalars(
        select(Control)
        .where(Control.engagement_id == file.engagement_id, Control.deleted_at.is_(None))
        .order_by(Control.libelle)
    )
    accounts = [
        {
            "compte": a.compte,
            "libelle": a.libelle,
            "solde_n": str(a.soldes.get("N", ZERO)),
            "branche": of[a.compte][0],
            "origine": of[a.compte][1],
        }
        for a in items
    ]
    return {
        "branches": branches,
        "comptes": accounts,
        "non_rattaches": [c["compte"] for c in accounts if c["branche"] is None],
        "etats": states,
        "ratios": ratios,
        "controles": [
            {"id": str(c.id), "libelle": c.libelle, "branche": c.branche} for c in controls
        ],
    }


@router.get("/audit-files/{file_id}/branches")
def read_branches(file_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    file, _ = get_file(db, file_id, user)
    return build(db, file)


def _check(db: Session, file: AuditFile, branche: str | None) -> None:
    _, branches = framework_branches(db, file)
    if branche is not None and branche not in {b["code"] for b in branches}:
        raise HTTPException(422, "Branche inconnue du référentiel")


@router.put("/audit-files/{file_id}/branches/accounts/{compte}")
def set_account(
    file_id: uuid.UUID, compte: str, body: BranchIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    _check(db, file, body.branche)
    current = _manual(db, file.id).get(compte)
    if body.branche is None:  # retour au rattachement du plan
        if current is not None:
            current.deleted_at, current.deleted_by = dt.datetime.now(dt.UTC), user.id
    elif current is None:
        db.add(
            AccountBranch(
                engagement_id=file.engagement_id,
                audit_file_id=file.id,
                compte=compte,
                branche=body.branche,
            )
        )
    else:
        current.branche = body.branche
    db.commit()
    return build(db, file)


@router.put("/audit-files/{file_id}/branches/controls/{control_id}")
def set_control(
    file_id: uuid.UUID, control_id: uuid.UUID, body: BranchIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    _check(db, file, body.branche)
    control = db.get(Control, control_id)
    if (
        control is None
        or control.deleted_at is not None
        or control.engagement_id != file.engagement_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contrôle introuvable dans la mission")
    control.branche = body.branche
    db.commit()
    return build(db, file)
