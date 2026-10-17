"""CON-03 : preuves liées aux constats."""

import io

import polars as pl

from tests.data_helpers import make_dataset
from tests.finding_helpers import create_finding, team  # noqa: F401


def test_con03_preuves(client, team, db):  # noqa: F811
    f = create_finding(client, team)
    url = f"/api/findings/{f['id']}/evidence"
    h = team["aud"].headers
    att = client.post(f"/api/workpapers/{team['wp']['id']}/attachments",
                      files={"file": ("contrat.pdf", io.BytesIO(b"%PDF-1.4 contrat"))}, headers=h).json()  # fmt: skip
    ds = make_dataset(db, team["mission"]["id"], pl.DataFrame({"fournisseur": ["X"]}), "Créations")
    for body in (
        {"type": "papier", "workpaper_id": team["wp"]["id"]},
        {"type": "piece_jointe", "attachment_id": att["id"], "commentaire": "Contrat non signé"},
        {"type": "table", "dataset_id": str(ds.id)},
    ):
        resp = client.post(url, json=body, headers=h)
        assert resp.status_code == 201, resp.text
    listed = client.get(url, headers=team["directeur"].headers).json()
    assert [e["type"] for e in listed] == ["papier", "piece_jointe", "table"]
    assert listed[0]["libelle"] == "A-1 · Créations de fournisseurs"
    assert listed[1]["libelle"] == "contrat.pdf" and listed[1]["empreinte"] == att["sha256"]
    assert listed[1]["workpaper_id"] == team["wp"]["id"]
    assert listed[2]["empreinte"] == ds.parquet_sha256 == listed[2]["empreinte_actuelle"]
    assert listed[2]["extrait"] == {"nb_lignes": 1, "operation": "import"}
    # Retrait.
    assert client.delete(f"/api/evidence/{listed[0]['id']}", headers=h).status_code == 204
    assert len(client.get(url, headers=h).json()) == 2
    assert client.delete(f"/api/evidence/{listed[0]['id']}", headers=h).status_code == 404


def test_con03_controles(client, team, db, account):  # noqa: F811
    from app.models import Finding
    from app.security.roles import Role
    from tests import helpers

    f = create_finding(client, team)
    url = f"/api/findings/{f['id']}/evidence"
    h = team["aud"].headers
    for body in (
        {"type": "papier", "workpaper_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "piece_jointe"},
        {"type": "table", "dataset_id": "00000000-0000-0000-0000-000000000000"},
        {"type": "autre"},
    ):
        assert client.post(url, json=body, headers=h).status_code == 422
    chef2 = account(Role.CHEF_MISSION)
    other = helpers.mission(client, chef2.headers)
    foreign = make_dataset(db, other["id"], pl.DataFrame({"a": [1]}))
    assert (
        client.post(
            url, json={"type": "table", "dataset_id": str(foreign.id)}, headers=h
        ).status_code
        == 422
    )
    assert client.post(url, json={"type": "papier", "workpaper_id": team["wp"]["id"]},
                       headers=team["da"].headers).status_code == 403  # fmt: skip
    finding = db.get(Finding, f["id"])
    finding.statut = "valide"
    db.commit()
    assert (
        client.post(
            url, json={"type": "papier", "workpaper_id": team["wp"]["id"]}, headers=h
        ).status_code
        == 409
    )
