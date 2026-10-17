"""Lancement d'une analyse et lecture de son résultat dans les tests du lot 6."""

import polars as pl

from app.analytics.store import absolute


def analyse(client, ctx, ds, operation, params=None, second=None, status=202, **extra):
    body = {"operation": operation, "parametres": params or {}, **extra}
    if second is not None:
        body["seconde_table_id"] = str(second.id)
    resp = client.post(f"/api/datasets/{ds.id}/analyses", json=body, headers=ctx["da"].headers)
    assert resp.status_code == status, resp.text
    return resp.json()


def result_df(db, result) -> pl.DataFrame:
    from app.models import Dataset

    ds = db.get(Dataset, result["id"])
    db.refresh(ds)
    assert ds.statut == "pret", ds.erreur
    return pl.read_parquet(absolute(ds.chemin_parquet))
