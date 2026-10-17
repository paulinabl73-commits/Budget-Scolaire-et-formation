import os
import uuid

import polars as pl
import pytest

from app.analytics.store import absolute, connect, is_read_only, parquet_ref, write_table
from app.models import Dataset
from app.security.roles import Role
from tests import helpers


@pytest.fixture
def ctx(client, account):
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    da = account(Role.DATA_ANALYST)
    m = helpers.mission(
        client, chef.headers, membres=[(aud.user, "auditeur"), (da.user, "data_analyst")]
    )
    return {"chef": chef, "aud": aud, "da": da, "mission": m, "url": f"/api/engagements/{m['id']}"}


def test_dat05_table_parquet_en_lecture_seule(client, ctx, db):
    eid = uuid.UUID(ctx["mission"]["id"])
    df = pl.DataFrame({"facture": ["F1", "F2"], "montant": [1250.5, 300.0]})
    written = write_table(df, eid)
    assert written.nb_lignes == 2 and written.nb_colonnes == 2
    assert [c["type"] for c in written.schema] == ["texte", "decimal"]
    assert is_read_only(written.chemin)
    assert oct(os.stat(absolute(written.chemin)).st_mode & 0o777) == "0o444"
    with connect() as con:
        total = con.execute(f"SELECT sum(montant) FROM {parquet_ref(written.chemin)}").fetchone()[0]
    assert total == 1550.5

    ds = Dataset(
        engagement_id=eid,
        nom="Factures",
        kind="import",
        statut="pret",
        chemin_parquet=written.chemin,
        nb_lignes=2,
        nb_colonnes=2,
        schema=written.schema,
        totaux_controle={},
        definition={},
        options={},
    )
    db.add(ds)
    db.commit()
    listed = client.get(f"{ctx['url']}/datasets", headers=ctx["da"].headers).json()
    assert [(d["nom"], d["lecture_seule"]) for d in listed] == [("Factures", True)]
    one = client.get(f"/api/datasets/{ds.id}", headers=ctx["aud"].headers).json()
    assert one["schema"][1]["nom"] == "montant"
    # Aucune route ne modifie une table importée.
    for method in ("put", "patch", "delete"):
        assert (
            getattr(client, method)(
                f"/api/datasets/{ds.id}", headers=ctx["chef"].headers
            ).status_code
            == 405
        )


def test_dat05_acces(client, ctx, account):
    assert (
        client.get(f"/api/datasets/{uuid.uuid4()}", headers=ctx["aud"].headers).status_code == 404
    )
    audite = account(Role.AUDITE)
    assert client.get(f"{ctx['url']}/datasets", headers=audite.headers).status_code == 404
    with pytest.raises(ValueError):
        absolute("../../etc/passwd")
