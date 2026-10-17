"""DAT-25 : macro tirée de l'historique, rejouée sur un nouveau fichier de même structure."""

from tests import data_files
from tests.analysis_helpers import analyse, result_df
from tests.test_datasets import ctx  # noqa: F401
from tests.test_imports import CSV_OPTIONS, run_import, upload
from tests.test_lignee import Ref, chain

CSV_2027 = (
    "N° facture;Fournisseur;Date;Montant TTC;Payée;Commentaire\n"
    "G-001;Alpha;31/01/2027;1 000,00;oui;x\n"
    "G-002;Alpha;15/02/2027;500,00;non;y\n"
    "G-003;Beta;28/02/2027;(10,00);oui;z\n"
).encode("cp1252")


def test_dat25_macro_rejouee(client, ctx, db):  # noqa: F811
    _, _, _, synthese = chain(client, ctx)
    resp = client.post(f"/api/datasets/{synthese['id']}/macro",
                       json={"nom": "TVA par fournisseur", "description": "Contrôle annuel"},
                       headers=ctx["da"].headers)  # fmt: skip
    assert resp.status_code == 201, resp.text
    macro = resp.json()
    assert len(macro["entrees"]) == 1
    assert {"nom": "Montant TTC", "type": "decimal"} in macro["entrees"][0]["colonnes"]
    assert [e["kind"] for e in macro["etapes"]] == ["vue", "analyse", "analyse"]
    assert macro["etapes"][2]["entrees"] == ["etape:1"]
    assert any(
        m["id"] == macro["id"] for m in client.get("/api/macros", headers=ctx["aud"].headers).json()
    )

    # Nouveau fichier, même structure (une colonne en plus est admise).
    up = upload(client, ctx, "factures_2027.csv", CSV_2027)
    new = run_import(client, ctx, up, CSV_OPTIONS, "Factures 2027")
    resp = client.post(f"/api/macros/{macro['id']}/run",
                       json={"entrees": [new["id"]], "suffixe": "(2027)"}, headers=ctx["aud"].headers)  # fmt: skip
    assert resp.status_code == 202, resp.text
    created = resp.json()
    assert [d["nom"] for d in created] == [
        "Factures TVA (2027)",
        f"{created[1]['nom']}",
        f"{created[2]['nom']}",
    ]
    statuses = [
        client.get(f"/api/datasets/{d['id']}", headers=ctx["aud"].headers).json() for d in created
    ]
    assert [s["statut"] for s in statuses] == ["pret", "pret", "pret"]
    from app.models import Dataset

    out = result_df(db, {"id": created[2]["id"]})
    assert out.columns == ["Fournisseur", "nombre", "somme_TVA"]
    assert [(f, str(t)) for f, _, t in out.rows()] == [("Alpha", "270.0000")]
    # La lignée de la nouvelle table remonte au nouveau fichier.
    graph = client.get(
        f"/api/datasets/{created[2]['id']}/lineage", headers=ctx["aud"].headers
    ).json()
    assert graph["noeuds"][0]["id"] == new["id"]
    assert db.get(Dataset, created[2]["id"]).definition["macro_id"] == macro["id"]


def test_dat25_structure_differente_et_erreurs(client, ctx):  # noqa: F811
    source, _, _, synthese = chain(client, ctx)
    macro = client.post(f"/api/datasets/{synthese['id']}/macro", json={"nom": "M"},
                        headers=ctx["da"].headers).json()  # fmt: skip
    other = upload(client, ctx, "autre.csv", b"code;valeur\nA;1\n")
    other_ds = run_import(client, ctx, other, None, "Autre")
    resp = client.post(f"/api/macros/{macro['id']}/run", json={"entrees": [other_ds["id"]]},
                       headers=ctx["aud"].headers)  # fmt: skip
    assert resp.status_code == 422 and "colonne « N° facture » absente" in resp.text
    retyped = dict(CSV_OPTIONS, colonnes=[{"nom": "Montant TTC", "type": "texte"}])
    up = upload(client, ctx, "f.csv", data_files.CSV_FR)
    texte = run_import(client, ctx, up, retyped, "Texte")
    resp = client.post(f"/api/macros/{macro['id']}/run", json={"entrees": [texte["id"]]},
                       headers=ctx["aud"].headers)  # fmt: skip
    assert resp.status_code == 422 and "date attendu" in resp.text
    resp = client.post(f"/api/macros/{macro['id']}/run",
                       json={"entrees": [source["id"], source["id"]]}, headers=ctx["aud"].headers)  # fmt: skip
    assert resp.status_code == 422 and "1 table(s) d'entrée attendue(s)" in resp.text
    # Une table source sans opération ne fait pas une macro.
    resp = client.post(f"/api/datasets/{source['id']}/macro", json={"nom": "Vide"},
                       headers=ctx["da"].headers)  # fmt: skip
    assert resp.status_code == 422
    assert client.post("/api/macros/00000000-0000-0000-0000-000000000000/run",
                       json={"entrees": [source["id"]]}, headers=ctx["aud"].headers).status_code == 404  # fmt: skip


def test_dat25_etape_en_erreur_arrete_la_suite(client, ctx):  # noqa: F811
    _, _, _, synthese = chain(client, ctx)
    macro = client.post(f"/api/datasets/{synthese['id']}/macro", json={"nom": "M"},
                        headers=ctx["da"].headers).json()  # fmt: skip
    # Même structure, mais aucune ligne ne passe l'extraction : la synthèse reste calculable.
    up = upload(
        client,
        ctx,
        "neg.csv",
        "N° facture;Fournisseur;Date;Montant TTC;Payée\nX;A;01/01/2027;(5,00);oui\n".encode(
            "cp1252"
        ),
    )
    neg = run_import(client, ctx, up, CSV_OPTIONS, "Négatifs")
    created = client.post(f"/api/macros/{macro['id']}/run", json={"entrees": [neg["id"]]},
                          headers=ctx["aud"].headers).json()  # fmt: skip
    final = client.get(f"/api/datasets/{created[2]['id']}", headers=ctx["aud"].headers).json()
    assert final["statut"] == "pret" and final["nb_lignes"] == 0
    # Une étape en erreur fait échouer les suivantes.
    source = run_import(
        client, ctx, upload(client, ctx, "f.csv", data_files.CSV_FR), CSV_OPTIONS, "F"
    )
    sample = analyse(client, ctx, Ref(source), "echantillon", {"methode": "aleatoire", "taille": 2})
    total = analyse(client, ctx, Ref(sample), "synthese", {"groupes": ["Fournisseur"]})
    macro = client.post(f"/api/datasets/{total['id']}/macro", json={"nom": "M2"},
                        headers=ctx["da"].headers).json()  # fmt: skip
    created = client.post(f"/api/macros/{macro['id']}/run", json={"entrees": [neg["id"]]},
                          headers=ctx["aud"].headers).json()  # fmt: skip
    states = [
        client.get(f"/api/datasets/{d['id']}", headers=ctx["aud"].headers).json() for d in created
    ]
    assert [d["statut"] for d in states] == ["erreur", "erreur"]
    assert "plus grand que la population" in states[0]["erreur"]
    assert states[1]["erreur"].startswith("Étape précédente en erreur")
