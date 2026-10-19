"""NF-08 : purge des données analysées après leur durée de conservation (RGPD)."""

import datetime as dt

import polars as pl
import pytest
from sqlalchemy import select

from app.analytics.retention import purge
from app.analytics.store import absolute
from app.audit.listeners import AuditIntegrityError
from app.cli import main as cli
from app.models import AuditLog, Dataset, Engagement, Upload
from app.storage import get_storage
from tests import helpers
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401
from tests.test_imports import upload


def _close(db, engagement_id, years_ago):
    e = db.get(Engagement, engagement_id)
    e.statut = "cloturee"
    e.cloturee_le = dt.datetime.now(dt.UTC) - dt.timedelta(days=365 * years_ago)
    db.commit()


def test_nf08_purge_apres_conservation(client, ctx, db, account, capsys):  # noqa: F811
    df = pl.DataFrame({"matricule": ["M1", "M2"], "salaire": [450_000.0, 380_000.0]})
    old = make_dataset(db, ctx["mission"]["id"], df, "Paie 2019")
    source = upload(client, ctx, "paie.csv", b"matricule;salaire\nM1;450000\n")
    recent_mission = helpers.mission(client, ctx["chef"].headers, titre="Mission récente")
    recent = make_dataset(db, recent_mission["id"], df, "Paie 2025")
    sha, totals = old.parquet_sha256, old.totaux_controle
    _close(db, ctx["mission"]["id"], 6)
    _close(db, recent_mission["id"], 1)

    assert cli(["purge-donnees", "--simulation"]) == 0
    assert "1 table(s), 1 fichier(s) à purger" in capsys.readouterr().out
    assert absolute(old.chemin_parquet).exists()

    report = purge(db)
    assert [(r["mission"], r["tables"], r["fichiers"]) for r in report] == [
        (ctx["mission"]["reference"], 1, 1)]  # fmt: skip
    db.expire_all()
    purged = db.get(Dataset, old.id)
    assert purged.statut == "purge" and purged.purge_le is not None
    assert not absolute(purged.chemin_parquet).exists()
    assert (purged.parquet_sha256, purged.totaux_controle) == (sha, totals)  # trace conservée
    stored = db.get(Upload, source["id"])
    assert stored.purge_le is not None and not get_storage().exists(stored.storage_key)
    assert db.get(Dataset, recent.id).statut == "pret"  # conservation non échue
    rows = client.post(f"/api/datasets/{old.id}/rows", json={}, headers=ctx["aud"].headers)
    assert rows.status_code == 409 and "purgées" in rows.text, rows.text
    event = db.scalar(select(AuditLog).where(AuditLog.action == "purge_conservation"))
    assert event is not None and event.apres["tables"] == 1
    assert purge(db) == []  # idempotent
    # Hors purge, le verrou de la mission clôturée reste entier.
    purged.nom = "Renommée"
    with pytest.raises(AuditIntegrityError):
        db.commit()
    db.rollback()
