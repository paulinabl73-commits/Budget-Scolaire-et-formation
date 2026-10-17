"""DAT-30 : table de résultat jointe à un papier de travail."""

import polars as pl

from app.richtext import from_plain_text
from app.security.roles import Role
from tests import helpers
from tests.analysis_helpers import analyse
from tests.data_helpers import make_dataset
from tests.test_datasets import ctx  # noqa: F401


def workpaper(client, ctx):  # noqa: F811
    resp = client.post(
        f"{ctx['url']}/workpapers",
        json={
            "reference": "D-1",
            "titre": "Doublons fournisseurs",
            "travaux": from_plain_text("x"),
            "conclusion": "Doublons à investiguer",
            "evaluation": "inefficace",
        },
        headers=ctx["aud"].headers,
    )
    assert resp.status_code == 201
    return resp.json()


def test_dat30_joindre_table_historique_graphique(client, ctx, db):  # noqa: F811
    df = pl.DataFrame({"fournisseur": ["A", "B", "A", "C", "A"], "montant": [10, 20, 30, 5, 1]})
    source = make_dataset(db, ctx["mission"]["id"], df, "Paiements")
    result = analyse(client, ctx, source, "doublons", {"cles": ["fournisseur"]})
    wp = workpaper(client, ctx)
    signed = client.post(f"/api/workpapers/{wp['id']}/signoffs", json={"type": "prepare"},
                         headers=ctx["aud"].headers)  # fmt: skip
    assert signed.status_code == 201, signed.text
    url = f"/api/workpapers/{wp['id']}/data-links"
    body = {"dataset_id": result["id"], "commentaire": "3 paiements en double",
            "graphique": {"categorie": "fournisseur", "valeur": "montant"}}  # fmt: skip
    resp = client.post(url, json=body, headers=ctx["aud"].headers)
    assert resp.status_code == 201, resp.text
    link = resp.json()
    assert link["dataset_nom"] == result["nom"] and link["nb_lignes"] == 3
    assert link["empreinte"] == result["parquet_sha256"] == link["empreinte_actuelle"]
    assert [n["operation"] for n in link["lignee"]["noeuds"]] == ["import", "doublons"]
    assert link["graphique"]["points"] == [{"etiquette": "A", "valeur": 41.0}]
    # La signature « préparé » est annulée : le contenu du papier a changé.
    wp_after = client.get(f"/api/workpapers/{wp['id']}", headers=ctx["aud"].headers).json()
    assert wp_after["statut_signature"] == "brouillon"
    listed = client.get(url, headers=ctx["chef"].headers).json()
    assert len(listed) == 1
    # Benford : graphique de la distribution par défaut.
    amounts = make_dataset(
        db, ctx["mission"]["id"], pl.DataFrame({"m": [float(10 + i) for i in range(200)]})
    )
    benford = analyse(client, ctx, amounts, "benford", {"champ": "m"})
    link2 = client.post(url, json={"dataset_id": benford["id"]}, headers=ctx["aud"].headers).json()
    assert link2["graphique"]["type"] == "benford" and len(link2["graphique"]["chiffres"]) == 9
    # Retrait du lien.
    assert (
        client.delete(f"/api/data-links/{link['id']}", headers=ctx["aud"].headers).status_code
        == 204
    )
    assert len(client.get(url, headers=ctx["aud"].headers).json()) == 1
    assert (
        client.delete(f"/api/data-links/{link['id']}", headers=ctx["aud"].headers).status_code
        == 404
    )


def test_dat30_controles(client, ctx, db, account):  # noqa: F811
    wp = workpaper(client, ctx)
    url = f"/api/workpapers/{wp['id']}/data-links"
    ds = make_dataset(db, ctx["mission"]["id"], pl.DataFrame({"a": ["x"], "b": ["y"]}))
    # Le data analyst lit les papiers mais ne les rédige pas.
    assert (
        client.post(url, json={"dataset_id": str(ds.id)}, headers=ctx["da"].headers).status_code
        == 403
    )
    bad = client.post(url, json={"dataset_id": str(ds.id), "graphique": {"categorie": "z"}},
                      headers=ctx["aud"].headers)  # fmt: skip
    assert bad.status_code == 422
    bad = client.post(url, json={"dataset_id": str(ds.id), "graphique": {"categorie": "a", "valeur": "b"}},
                      headers=ctx["aud"].headers)  # fmt: skip
    assert bad.status_code == 422 and "numérique" in bad.text
    # Table d'une autre mission.
    chef2 = account(Role.CHEF_MISSION)
    other = helpers.mission(client, chef2.headers, membres=[(ctx["aud"].user, "auditeur")])
    foreign = make_dataset(db, other["id"], pl.DataFrame({"a": [1]}))
    resp = client.post(url, json={"dataset_id": str(foreign.id)}, headers=ctx["aud"].headers)
    assert resp.status_code == 422 and "même mission" in resp.text
