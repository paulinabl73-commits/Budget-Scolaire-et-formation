"""RCO-27 : transmission d'un dossier de clôture au Module 5 lorsque l'entité est aussi auditée.

L'expert-comptable transmet le dossier, une fois son visa de revue donné (RCO-23), à la mission
d'audit dont l'entité lui communique la référence : l'entité du portefeuille du cabinet et celle
de l'univers d'audit sont distinctes, et aucune des deux équipes ne voit les dossiers de
l'autre. Le chef de cette mission crée alors son propre dossier par reprise, sans
ressaisie : balance N révisée des écritures acceptées, balance N-1, balances auxiliaires,
affectations manuelles des comptes et justificatifs (pièces et justifications de comptes)
regroupés dans un papier de travail. Le dossier d'audit reste distinct du dossier de clôture :
les travaux et ajustements de l'auditeur ne modifient pas les comptes présentés par le cabinet.
Le grand livre n'est pas repris : l'auditeur l'obtient directement de l'entité.
"""

import datetime as dt
import io
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.api.audit_files import AuditFileIn, AuditFileOut, can_direct, create_file, file_out
from app.api.deps import CurrentUser, DbSession
from app.api.mission_access import get_engagement
from app.api.pieces import _closing, _pieces
from app.api.portfolio import can_manage_client
from app.audit.listeners import record_event
from app.models.engagement import Engagement
from app.models.portfolio import AccountJustification, Client, ClientFile, Closing
from app.models.revision import AccountMapping, AuditFile, TrialBalance, TrialBalanceLine
from app.models.user import User
from app.models.workpaper import Attachment, Workpaper
from app.revision.balances import AMOUNTS, BalanceLine, _split
from app.revision.imports import balance_lines, totals
from app.revision.mapping import adjustment_nets
from app.richtext import from_plain_text
from app.storage import get_storage

router = APIRouter(tags=["Portefeuille (Module 6)"])
ZERO = Decimal(0)


class FromClosingIn(BaseModel):
    closing_id: uuid.UUID


class TransmitIn(BaseModel):
    mission: str = Field(min_length=3, max_length=40)  # référence de la mission d'audit


def _reprises(db: Session, closing: Closing) -> list[AuditFile]:
    return list(
        db.scalars(
            select(AuditFile).where(
                AuditFile.source_file_id == closing.audit_file_id, AuditFile.deleted_at.is_(None)
            )
        )
    )


def transmission_out(db: Session, closing: Closing) -> dict[str, Any]:
    return {
        "transmis_le": closing.transmis_le.isoformat() if closing.transmis_le else None,
        "transmis_par": db.get(User, closing.transmis_par).nom if closing.transmis_par else None,
        "mission": db.get(Engagement, closing.transmis_a).reference if closing.transmis_a else None,
        "reprises": [
            {"dossier_id": str(f.id), "mission": db.get(Engagement, f.engagement_id).reference}
            for f in _reprises(db, closing)
        ],
    }


def _expert(db: Session, closing_id: uuid.UUID, user: User) -> Closing:
    closing, client = _closing(db, closing_id, user)
    if not can_manage_client(client, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Réservé à l'expert-comptable")
    return closing


@router.get("/closings/{closing_id}/transmission")
def read_transmission(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing, _ = _closing(db, closing_id, user)
    return transmission_out(db, closing)


@router.post("/closings/{closing_id}/transmission")
def transmit(
    closing_id: uuid.UUID, body: TransmitIn, user: CurrentUser, db: DbSession
) -> dict[str, Any]:
    closing = _expert(db, closing_id, user)
    if "expert" not in (closing.revues or {}):
        raise HTTPException(status.HTTP_409_CONFLICT, "Visa de revue de l'expert-comptable attendu")
    if _reprises(db, closing):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier déjà repris par la mission d'audit")
    target = db.scalar(
        select(Engagement).where(
            Engagement.reference == body.mission.strip(),
            Engagement.mode == "audit",
            Engagement.entity_id.is_not(None),
            Engagement.deleted_at.is_(None),
        )
    )
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mission d'audit introuvable")
    closing.transmis_le, closing.transmis_par = dt.datetime.now(dt.UTC), user.id
    closing.transmis_a = target.id
    record_event(db, "transmission", object_type="Closing", object_id=closing.id,
                 details={"mission": target.reference})  # fmt: skip
    db.commit()
    return transmission_out(db, closing)


@router.delete("/closings/{closing_id}/transmission")
def withdraw(closing_id: uuid.UUID, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    closing = _expert(db, closing_id, user)
    if _reprises(db, closing):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier déjà repris par la mission d'audit")
    closing.transmis_le = closing.transmis_par = closing.transmis_a = None
    db.commit()
    return transmission_out(db, closing)


def _audit_engagement(db: Session, engagement_id: uuid.UUID, user: User) -> Engagement:
    engagement = get_engagement(db, engagement_id, user)
    if engagement.mode != "audit" or not can_direct(engagement, user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Réservé au chef de mission d'une mission d'audit"
        )
    return engagement


def _available(db: Session, engagement: Engagement) -> list[tuple[Closing, Client]]:
    """Clôtures transmises à la mission (sans accès au portefeuille du cabinet)."""
    rows = db.execute(
        select(Closing, Client)
        .join(Client, Client.id == Closing.client_id)
        .where(Closing.transmis_a == engagement.id, Closing.deleted_at.is_(None))
        .order_by(Closing.exercice.desc())
    )
    return [(c, cl) for c, cl in rows]


@router.get("/engagements/{engagement_id}/transmitted-closings")
def transmitted(engagement_id: uuid.UUID, user: CurrentUser, db: DbSession) -> list[dict[str, Any]]:
    engagement = _audit_engagement(db, engagement_id, user)
    return [
        {"id": str(c.id), "client": cl.raison_sociale, "exercice": c.exercice,
         "transmis_le": c.transmis_le.isoformat(), "repris": bool(_reprises(db, c))}
        for c, cl in _available(db, engagement)
    ]  # fmt: skip


def _copy_balance(
    db: Session, tb: TrialBalance, target: AuditFile, nets: dict[str, Decimal] | None
) -> None:
    """Copie une balance ; avec `nets`, y intègre les écritures acceptées (balance révisée)."""
    lines = balance_lines(db, tb)
    if nets:
        by_account = {ln.compte: ln for ln in lines}
        for compte, net in nets.items():
            ln = by_account.get(compte)
            if ln is None:
                ln = by_account[compte] = BalanceLine(compte, None, dict.fromkeys(AMOUNTS, ZERO))
                lines.append(ln)
            debit, credit = _split(net)
            ln.amounts["mouvement_debit"] += debit
            ln.amounts["mouvement_credit"] += credit
            ln.amounts["solde_debit"], ln.amounts["solde_credit"] = _split(ln.net("solde") + net)
    copy = TrialBalance(
        engagement_id=target.engagement_id,
        audit_file_id=target.id,
        periode=tb.periode,
        type=tb.type,
        logiciel=tb.logiciel,
        nom_fichier=(f"Balance révisée – clôture {target.exercice}" if nets else tb.nom_fichier),
        sha256=None if nets else tb.sha256,
        storage_key=None if nets else tb.storage_key,
        statut="accepte",
        anomalies=[],
        avertissements=tb.avertissements,
        totaux=totals(lines),
        nb_lignes=len(lines),
        devise_source=tb.devise_source,
        cours=tb.cours,
        compte_collectif=tb.compte_collectif,
    )
    db.add(copy)
    db.flush()
    if lines:
        db.execute(
            insert(TrialBalanceLine),
            [{"id": uuid.uuid4(), "trial_balance_id": copy.id, "compte": ln.compte,
              "libelle": ln.libelle, **ln.amounts} for ln in sorted(lines, key=lambda x: x.compte)],
        )  # fmt: skip


def _copy_mappings(db: Session, source: AuditFile, target: AuditFile) -> None:
    current = {
        m.compte: m
        for m in db.scalars(
            select(AccountMapping).where(
                AccountMapping.audit_file_id == target.id, AccountMapping.deleted_at.is_(None)
            )
        )
    }
    for m in db.scalars(
        select(AccountMapping).where(
            AccountMapping.audit_file_id == source.id, AccountMapping.deleted_at.is_(None)
        )
    ):
        row = current.get(m.compte)
        if row is None:
            row = AccountMapping(
                engagement_id=target.engagement_id, audit_file_id=target.id, compte=m.compte
            )
            db.add(row)
        row.poste, row.poste_crediteur, row.commentaire = m.poste, m.poste_crediteur, m.commentaire


def _copy_documents(
    db: Session, closing: Closing, client: Client, target: AuditFile, user: User
) -> Workpaper:
    justifications = list(
        db.scalars(
            select(AccountJustification)
            .where(
                AccountJustification.audit_file_id == closing.audit_file_id,
                AccountJustification.deleted_at.is_(None),
            )
            .order_by(AccountJustification.compte)
        )
    )
    pieces = _pieces(db, closing)
    owners = {j.id: f"Justification du compte {j.compte}" for j in justifications}
    owners |= {p.id: f"Pièce : {p.libelle}" for p in pieces}
    files = list(
        db.scalars(
            select(ClientFile)
            .where(ClientFile.objet_id.in_(list(owners)), ClientFile.deleted_at.is_(None))
            .order_by(ClientFile.created_at)
        )
    ) if owners else []  # fmt: skip
    text = [f"Reprise du dossier de clôture {closing.exercice} de {client.raison_sociale}."]
    text += [
        f"Compte {j.compte} : justifié {'—' if j.montant_justifie is None else j.montant_justifie}"
        + (f" – {j.commentaire}" if j.commentaire else "")
        for j in justifications
    ]
    text += [f"{owners[f.objet_id]} – {f.nom_fichier} (empreinte {f.sha256[:12]}…)" for f in files]
    wp = Workpaper(
        engagement_id=target.engagement_id,
        reference=f"CLO-{closing.exercice}",
        titre=f"Justificatifs repris du dossier de clôture {closing.exercice}",
        objectif="Pièces et justifications de comptes transmises par l'expert-comptable (RCO-27)",
        travaux=from_plain_text("\n".join(text)),
        version=1,
    )
    db.add(wp)
    db.flush()
    storage = get_storage()
    for f in files:
        stored = storage.put(
            f"attachments/{target.engagement_id}/{uuid.uuid4()}",
            io.BytesIO(b"".join(storage.open(f.storage_key))),
        )
        db.add(
            Attachment(
                engagement_id=target.engagement_id, workpaper_id=wp.id, nom_fichier=f.nom_fichier,
                content_type=f.content_type, taille=stored.size, sha256=stored.sha256,
                storage_key=stored.key,
            )
        )  # fmt: skip
    return wp


@router.post("/engagements/{engagement_id}/audit-files/from-closing", status_code=201)
def from_closing(
    engagement_id: uuid.UUID, body: FromClosingIn, user: CurrentUser, db: DbSession
) -> AuditFileOut:
    engagement = _audit_engagement(db, engagement_id, user)
    match = next(((c, cl) for c, cl in _available(db, engagement) if c.id == body.closing_id), None)
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clôture non transmise à cette mission")
    closing, client = match
    if _reprises(db, closing):
        raise HTTPException(status.HTTP_409_CONFLICT, "Dossier de clôture déjà repris")
    source = db.get(AuditFile, closing.audit_file_id)
    created = create_file(
        engagement.id,
        AuditFileIn(
            exercice=source.exercice,
            date_debut=source.date_debut,
            date_fin=source.date_fin,
            framework_id=source.framework_id,
            ifrs_framework_id=source.ifrs_framework_id,
            devise=source.devise,
            pays=source.pays,
        ),
        user,
        db,
    )
    target = db.get(AuditFile, created.id)
    try:
        _fill(db, closing, client, source, target, user)
    except Exception:
        db.rollback()  # create_file a validé le dossier : il est retiré si la reprise échoue
        target = db.get(AuditFile, created.id)
        target.deleted_at, target.deleted_by = dt.datetime.now(dt.UTC), user.id
        db.commit()
        raise
    db.commit()
    return file_out(db, target, engagement, user)


def _fill(
    db: Session, closing: Closing, client: Client, source: AuditFile, target: AuditFile, user: User
) -> None:
    target.source_file_id = source.id
    nets = adjustment_nets(db, source.id)
    for tb in db.scalars(
        select(TrialBalance).where(
            TrialBalance.audit_file_id == source.id,
            TrialBalance.statut == "accepte",
            TrialBalance.deleted_at.is_(None),
            TrialBalance.dataset_id.is_(None),
        )
    ):
        revised = tb.periode == "N" and tb.type == "balance"
        _copy_balance(db, tb, target, nets if revised else None)
    _copy_mappings(db, source, target)
    _copy_documents(db, closing, client, target, user)
    record_event(db, "reprise_cloture", object_type="AuditFile", object_id=target.id,
                 details={"cloture": str(closing.id)})  # fmt: skip
