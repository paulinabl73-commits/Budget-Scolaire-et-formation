"""Feuilles maîtresses par cycle (REV-15) : soldes N-1 et N, ajustements acceptés, solde
révisé, compte par compte, avec renvoi aux papiers de travail.

Les soldes sont nets (débit − crédit). Les papiers rattachés au cycle et ceux qui fondent ses
écritures d'ajustement sont cités ; les écritures encore proposées ou refusées sont listées
à part, sans effet sur le solde révisé.
"""

import datetime as dt
import uuid
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.adjustments import file_adjustments, lines_of
from app.api.audit_files import get_file, require_work
from app.api.deps import CurrentUser, DbSession
from app.api.risk_matrix import file_cycles
from app.models.revision import AuditFile, LeadScheduleReference
from app.models.workpaper import Workpaper
from app.revision.cycles import cycle_of
from app.revision.mapping import assignments

router = APIRouter(tags=["Révision – feuilles maîtresses"])
ZERO = Decimal(0)


class ReferencesIn(BaseModel):
    workpaper_ids: list[uuid.UUID] = Field(max_length=100)


def _references(db: Session, file_id: uuid.UUID) -> dict[str, list[LeadScheduleReference]]:
    out: dict[str, list[LeadScheduleReference]] = defaultdict(list)
    for ref in db.scalars(
        select(LeadScheduleReference).where(
            LeadScheduleReference.audit_file_id == file_id,
            LeadScheduleReference.deleted_at.is_(None),
        )
    ):
        out[ref.cycle].append(ref)
    return out


def lead_schedules(db: Session, file: AuditFile) -> list[dict[str, Any]]:
    cycles = file_cycles(db, file)
    adjustments = file_adjustments(db, file.id)
    lines = lines_of(db, [a.id for a in adjustments])
    accepted: dict[str, Decimal] = defaultdict(Decimal)
    by_cycle_adj: dict[str, set[int]] = defaultdict(set)
    adj_papers: dict[str, set[uuid.UUID]] = defaultdict(set)
    for adj in adjustments:
        for ln in lines[adj.id]:
            code = cycle_of(ln.compte, cycles)
            if adj.statut == "acceptee":
                accepted[ln.compte] += ln.debit - ln.credit
            if code:
                by_cycle_adj[code].add(adj.numero)
                if adj.workpaper_id:
                    adj_papers[code].add(adj.workpaper_id)
    status_of = {a.numero: a.statut for a in adjustments}
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for a in assignments(db, file):
        seen.add(a.compte)
        n1, n = a.soldes.get("N-1", ZERO), a.soldes.get("N", ZERO)
        adj = accepted.get(a.compte, ZERO)
        rows[cycle_of(a.compte, cycles) or "hors_cycle"].append(
            {
                "compte": a.compte,
                "libelle": a.libelle,
                "N-1": n1,
                "N": n,
                "ajustements": adj,
                "revise": n + adj,
            }  # fmt: skip
        )
    for compte, adj in accepted.items():  # compte créé par une écriture d'ajustement
        if compte not in seen:
            rows[cycle_of(compte, cycles) or "hors_cycle"].append(
                {
                    "compte": compte,
                    "libelle": None,
                    "N-1": ZERO,
                    "N": ZERO,
                    "ajustements": adj,
                    "revise": adj,
                }  # fmt: skip
            )
    refs = _references(db, file.id)
    papers = {
        wp.id: wp
        for wp in db.scalars(
            select(Workpaper).where(
                Workpaper.engagement_id == file.engagement_id, Workpaper.deleted_at.is_(None)
            )
        )
    }
    out = []
    for c in cycles:
        accounts = sorted(rows.get(c["code"], []), key=lambda r: r["compte"])
        linked = {r.workpaper_id for r in refs.get(c["code"], [])} | adj_papers[c["code"]]
        out.append({
            "cycle": c["code"], "libelle": c["libelle"],
            "totaux": {k: str(sum((r[k] for r in accounts), ZERO))
                       for k in ("N-1", "N", "ajustements", "revise")},
            "comptes": [{**r, **{k: str(r[k]) for k in ("N-1", "N", "ajustements", "revise")}}
                        for r in accounts],
            "papiers": sorted(
                ({"id": str(p.id), "reference": p.reference, "titre": p.titre,
                  "rattache": p.id in {r.workpaper_id for r in refs.get(c["code"], [])}}
                 for p in (papers.get(i) for i in linked) if p is not None),
                key=lambda p: p["reference"]),
            "ecritures": [{"numero": n, "statut": status_of[n]}
                          for n in sorted(by_cycle_adj[c["code"]])],
        })  # fmt: skip
    return out


@router.get("/audit-files/{file_id}/lead-schedules")
def read_lead_schedules(
    file_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> list[dict[str, Any]]:
    file, _ = get_file(db, file_id, user)
    return lead_schedules(db, file)


@router.put("/audit-files/{file_id}/lead-schedules/{cycle}/workpapers")
def set_references(
    file_id: uuid.UUID, cycle: str, body: ReferencesIn, user: CurrentUser, db: DbSession
) -> list[dict[str, Any]]:
    file, engagement = get_file(db, file_id, user)
    require_work(file, engagement, user)
    if cycle not in {c["code"] for c in file_cycles(db, file)}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cycle inconnu")
    wanted = set(body.workpaper_ids)
    for wp_id in wanted:
        wp = db.get(Workpaper, wp_id)
        if wp is None or wp.deleted_at or wp.engagement_id != file.engagement_id:
            raise HTTPException(422, "Papier de travail inconnu dans la mission")
    current = {r.workpaper_id: r for r in _references(db, file.id).get(cycle, [])}
    now = dt.datetime.now(dt.UTC)
    for wp_id, ref in current.items():
        if wp_id not in wanted:
            ref.deleted_at, ref.deleted_by = now, user.id
    for wp_id in wanted - set(current):
        db.add(LeadScheduleReference(engagement_id=file.engagement_id, audit_file_id=file.id,
                                     cycle=cycle, workpaper_id=wp_id))  # fmt: skip
    db.commit()
    return lead_schedules(db, file)
