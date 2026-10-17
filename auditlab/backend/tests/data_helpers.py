"""Création directe de tables de référence pour les tests du Module 2."""

import uuid

import polars as pl
from sqlalchemy.orm import Session

from app.analytics.store import control_totals, file_sha256, write_table
from app.models import Dataset


def make_dataset(db: Session, engagement_id: str | uuid.UUID, df: pl.DataFrame, nom: str = "T"):
    eid = uuid.UUID(str(engagement_id))
    written = write_table(df, eid)
    ds = Dataset(
        engagement_id=eid,
        nom=nom,
        kind="import",
        statut="pret",
        chemin_parquet=written.chemin,
        nb_lignes=written.nb_lignes,
        nb_colonnes=written.nb_colonnes,
        schema=written.schema,
        totaux_controle=control_totals(written.chemin, written.schema),
        parquet_sha256=file_sha256(written.chemin),
        definition={},
        options={},
    )
    db.add(ds)
    db.commit()
    return ds
