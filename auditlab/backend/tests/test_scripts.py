"""DAT-26 : scripts Python d'analyse avec l'API simplifiée « audit »."""

import polars as pl

from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401
from tests.test_imports import upload

CODE = """
achats = audit.table("Achats")
print("lignes :", achats.height)
d = audit.duplicates(achats, ["fournisseur", "montant"])
audit.save(d, "Doublons achats")
audit.save(audit.benford(achats, "montant"), "Benford achats")
audit.save(audit.gaps(achats, "numero"), "Ruptures")
f = audit.import_csv("tiers.csv")
audit.metric("doublons", d.height)
audit.metric("total_tiers", f["solde"].sum())
"""


def test_dat26_script(client, ctx, db, account):  # noqa: F811
    da, aud = ctx["da"].headers, ctx["aud"].headers
    df = pl.DataFrame({"numero": [1, 2, 3, 6, 7], "fournisseur": ["A", "B", "A", "C", "A"],
                       "montant": [120.0, 35.5, 120.0, 980.0, 15.0]})  # fmt: skip
    achats = make_dataset(db, ctx["mission"]["id"], df, "Achats")
    up = upload(client, ctx, "tiers.csv", b"tiers;solde\nX;1 250,50\nY;-250,50\n")
    body = {"nom": "Contrôles achats", "code": CODE,
            "entrees": [{"type": "table", "id": str(achats.id)}, {"type": "fichier", "id": up["id"]}]}  # fmt: skip
    url = f"{ctx['url']}/scripts"
    bad = client.post(url, json={**body, "code": "def f(:\n"}, headers=da)
    assert bad.status_code == 422 and "ligne 1" in bad.json()["detail"]
    script = client.post(url, json=body, headers=da)
    assert script.status_code == 201, script.text
    sid = script.json()["id"]
    assert [e["nom"] for e in script.json()["entrees"]] == ["Achats", "tiers.csv"]
    run = client.post(f"/api/scripts/{sid}/runs", headers=da)
    assert run.status_code == 202
    run = client.get(f"/api/script-runs/{run.json()['id']}", headers=aud).json()
    assert run["statut"] == "termine", (run["erreur"], run["sortie"])
    assert "lignes : 5" in run["sortie"] and len(run["code_sha256"]) == 64
    assert run["indicateurs"] == {"doublons": 2.0, "total_tiers": 1000.0}
    tables = {t["nom"]: t for t in run["tables"]}
    assert tables["Doublons achats"]["nb_lignes"] == 2 and tables["Ruptures"]["nb_lignes"] == 1
    ds = client.get(f"/api/datasets/{tables['Benford achats']['id']}", headers=aud).json()
    assert ds["kind"] == "script"
    lineage = client.get(f"/api/datasets/{tables['Doublons achats']['id']}/lineage", headers=aud)
    assert lineage.status_code == 200 and str(achats.id) in lineage.text
    # Erreur du script : message et ligne, sans trace interne.
    client.put(f"/api/scripts/{sid}", json={**body, "code": "x = 1\naudit.table('Inconnue')\n"},
               headers=da)  # fmt: skip
    failed = client.post(f"/api/scripts/{sid}/runs", headers=da).json()
    failed = client.get(f"/api/script-runs/{failed['id']}", headers=da).json()
    assert failed["statut"] == "erreur" and "Inconnue" in failed["erreur"]
    client.put(f"/api/scripts/{sid}", json={**body, "code": "1 / 0\n"}, headers=da)
    failed = client.post(f"/api/scripts/{sid}/runs", headers=da).json()
    failed = client.get(f"/api/script-runs/{failed['id']}", headers=da).json()
    assert "ZeroDivisionError" in failed["erreur"] and "bootstrap" not in failed["erreur"]
    # Le script ne voit aucun secret de l'application.
    client.put(f"/api/scripts/{sid}", json={**body, "code": "import os\nprint(sorted(os.environ))\n"},
               headers=da)  # fmt: skip
    env = client.post(f"/api/scripts/{sid}/runs", headers=da).json()
    env = client.get(f"/api/script-runs/{env['id']}", headers=da).json()
    assert "DATABASE_URL" not in env["sortie"] and "SECRET" not in env["sortie"].upper()
    assert len(client.get(f"/api/scripts/{sid}/runs", headers=aud).json()) == 4
    assert client.post(f"/api/scripts/{sid}/runs", headers=aud).status_code == 202  # DATA_ANALYZE
    assert any(
        f["nom"] == "audit.duplicates" for f in client.get("/api/scripts/api", headers=aud).json()
    )


def test_dat26_fichiers_de_la_mission(client, ctx):  # noqa: F811
    up = upload(client, ctx, "tiers.csv", b"a;b\n1;2\n")
    files = client.get(f"{ctx['url']}/uploads", headers=ctx["aud"].headers).json()
    assert [f["id"] for f in files] == [up["id"]]
