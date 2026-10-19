"""Purge des données analysées après leur durée de conservation (NF-08, RGPD).

Les tables du Module 2 et les fichiers sources importés peuvent contenir des données
personnelles (paie, tiers, notes de frais). Ils sont purgés `conservation_donnees_mois` mois
après la clôture de la mission : les fichiers Parquet et sources sont supprimés, la sortie
console des scripts est effacée. Restent, comme trace de la preuve d'audit (ISA 230), les
métadonnées de chaque table : nom, schéma, nombre de lignes, empreinte SHA-256 et totaux de
contrôle. Chaque mission purgée est journalisée.
"""

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analytics.store import absolute
from app.audit.listeners import record_event
from app.cabinet.dates import add_months
from app.config import get_settings
from app.models.data import Dataset, DatasetStatus, ScriptRun, Upload
from app.models.engagement import Engagement
from app.storage import get_storage


def limit_date(now: dt.datetime) -> dt.datetime:
    months = get_settings().conservation_donnees_mois
    day = add_months(now.date(), -months)
    return dt.datetime.combine(day, now.timetz())


def expired_missions(db: Session, now: dt.datetime) -> list[Engagement]:
    return list(
        db.scalars(
            select(Engagement)
            .where(
                Engagement.statut == "cloturee",
                Engagement.cloturee_le.is_not(None),
                Engagement.cloturee_le < limit_date(now),
            )
            .order_by(Engagement.cloturee_le)
        )
    )


def purge(
    db: Session, now: dt.datetime | None = None, simulation: bool = False
) -> list[dict[str, Any]]:
    """Purge (ou recense, en simulation) les données des missions dont la conservation a expiré."""
    now = now or dt.datetime.now(dt.UTC)
    report = []
    db.info["purge_conservation"] = True
    try:
        for engagement in expired_missions(db, now):
            datasets = list(db.scalars(select(Dataset).where(
                Dataset.engagement_id == engagement.id, Dataset.purge_le.is_(None),
                Dataset.chemin_parquet.is_not(None))))  # fmt: skip
            uploads = list(db.scalars(select(Upload).where(
                Upload.engagement_id == engagement.id, Upload.purge_le.is_(None))))  # fmt: skip
            if not datasets and not uploads:
                continue
            report.append({"mission": engagement.reference, "tables": len(datasets),
                           "fichiers": len(uploads),
                           "cloturee_le": engagement.cloturee_le.isoformat()})  # fmt: skip
            if simulation:
                continue
            for ds in datasets:
                path = absolute(ds.chemin_parquet)
                if path.exists():
                    path.chmod(0o640)
                    path.unlink()
                ds.statut, ds.purge_le = DatasetStatus.PURGE.value, now
            for upload in uploads:
                get_storage().delete(upload.storage_key)
                upload.purge_le = now
            for run in db.scalars(
                select(ScriptRun).where(ScriptRun.engagement_id == engagement.id)
            ):
                run.sortie = ""
            record_event(db, "purge_conservation", object_type="Engagement",
                         object_id=engagement.id, details=report[-1])  # fmt: skip
            db.commit()
    finally:
        db.info["purge_conservation"] = False
    return report
