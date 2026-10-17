"""DAT-24 : lignée des tables ; NF-04 : rejeu depuis la source."""

from tests import data_files
from tests.analysis_helpers import analyse
from tests.test_datasets import ctx  # noqa: F401
from tests.test_imports import CSV_OPTIONS, run_import, upload


class Ref:
    def __init__(self, data):
        self.id = data["id"]


def chain(client, ctx):  # noqa: F811
    up = upload(client, ctx, "factures.csv", data_files.CSV_FR)
    source = run_import(client, ctx, up, CSV_OPTIONS, "Factures")
    view = client.post(
        f"/api/datasets/{source['id']}/views",
        json={
            "nom": "Factures TVA",
            "champs": [{"nom": "TVA", "expression": "[Montant TTC] * 0.18"}],
        },
        headers=ctx["da"].headers,
    ).json()
    extraction = analyse(client, ctx, Ref(view), "extraction", {"expression": "TVA > 0"})
    synthese = analyse(client, ctx, Ref(extraction), "synthese",
                       {"groupes": ["Fournisseur"], "agregats": [{"champ": "TVA", "fonction": "somme"}]})  # fmt: skip
    return source, view, extraction, synthese


def test_dat24_graphe_de_lignee(client, ctx):  # noqa: F811
    source, view, extraction, synthese = chain(client, ctx)
    resp = client.get(f"/api/datasets/{synthese['id']}/lineage", headers=ctx["chef"].headers)
    assert resp.status_code == 200
    graph = resp.json()
    nodes = graph["noeuds"]
    assert [n["id"] for n in nodes] == [source["id"], view["id"], extraction["id"], synthese["id"]]
    assert [n["niveau"] for n in nodes] == [0, 1, 2, 3]
    assert [n["operation"] for n in nodes] == ["import", "vue", "extraction", "synthese"]
    assert nodes[0]["source_sha256"] == source["source_sha256"]
    assert nodes[0]["parametres"]["upload_id"]
    assert nodes[2]["parametres"] == {"expression": "TVA > 0"}
    assert graph["aretes"] == sorted(
        [
            {"de": source["id"], "vers": view["id"]},
            {"de": view["id"], "vers": extraction["id"]},
            {"de": extraction["id"], "vers": synthese["id"]},
        ],
        key=lambda e: (e["de"], e["vers"]),
    )
    # Une source n'a pas d'ancêtre.
    alone = client.get(f"/api/datasets/{source['id']}/lineage", headers=ctx["aud"].headers).json()
    assert len(alone["noeuds"]) == 1 and alone["aretes"] == []


def test_dat24_jointure_deux_sources(client, ctx):  # noqa: F811
    source, _, extraction, _ = chain(client, ctx)
    joined = analyse(client, ctx, Ref(extraction), "jointure",
                     {"cles": [{"gauche": "N° facture", "droite": "N° facture"}]}, second=Ref(source))  # fmt: skip
    graph = client.get(f"/api/datasets/{joined['id']}/lineage", headers=ctx["aud"].headers).json()
    assert len(graph["noeuds"]) == 4
    assert {"de": source["id"], "vers": joined["id"]} in graph["aretes"]
    assert graph["noeuds"][-1]["niveau"] == 3  # source → vue → extraction → jointure


def test_nf04_rejeu_depuis_la_source(client, ctx, db):  # noqa: F811
    from app.models import Dataset

    _, _, extraction, synthese = chain(client, ctx)
    resp = client.post(f"/api/datasets/{synthese['id']}/replay", headers=ctx["aud"].headers)
    result = resp.json()
    assert result["identique"] is True
    assert [s["kind"] for s in result["etapes"]] == ["import", "vue", "analyse", "analyse"]
    assert all(s["identique"] in (True, None) for s in result["etapes"])
    # Une table dont l'empreinte enregistrée ne correspond plus est signalée.
    ds = db.get(Dataset, extraction["id"])
    ds.parquet_sha256 = "0" * 64
    db.commit()
    result = client.post(
        f"/api/datasets/{synthese['id']}/replay", headers=ctx["aud"].headers
    ).json()
    assert result["identique"] is False
    assert [s["identique"] for s in result["etapes"] if s["kind"] == "analyse"] == [False, True]
