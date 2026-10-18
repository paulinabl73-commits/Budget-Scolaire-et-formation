"""CIP-06 et CIP-07 : frais de gestion, réserves techniques et placements."""

from tests.cipres_helpers import detail_file, ops, ops_detail, ops_file, set_params  # noqa: F401
from tests.revision_helpers import create_file, rev  # noqa: F401


def test_cip06_frais_de_gestion(client, rev, ops_detail, db):  # noqa: F811
    f = detail_file(client, rev, ops_detail)
    url = f"/api/audit-files/{f['id']}/ops-indicators"
    data = client.get(url, headers=rev["aud"].headers).json()
    assert "plafond_frais_gestion" in data["parametres_manquants"]
    year = data["frais_gestion"]["exercices"][0]
    assert (year["exercice"], year["cotisations_encaissees"], year["variation_creances"]) == (
        2026,
        "95000000.00",
        "5000000.00",
    )
    assert (year["ratio"], year["conforme"]) == ("10.00", None)
    set_params(db, ops_detail, ("plafond_frais_gestion", "8", None))
    year = client.get(url, headers=rev["aud"].headers).json()["frais_gestion"]["exercices"][0]
    assert (year["plafond"], year["conforme"]) == ("8", False)


def test_cip06_postes_manquants_et_dossier_incomplet(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    data = client.get(
        f"/api/audit-files/{f['id']}/ops-indicators", headers=rev["aud"].headers
    ).json()
    assert data["frais_gestion"] == {"postes_manquants": ["COT", "CCO", "FGE"], "exercices": []}
    empty = create_file(client, rev, exercice=2027, framework_id=str(ops.id))
    assert (
        client.get(
            f"/api/audit-files/{empty['id']}/ops-indicators", headers=rev["aud"].headers
        ).status_code
        == 409
    )


def test_cip06_exercice_precedent(client, rev, ops_detail, db):  # noqa: F811
    from tests.cipres_helpers import DETAIL_N, balance_csv
    from tests.test_balances import upload

    detail_file(client, rev, ops_detail)
    f = create_file(client, rev, exercice=2027, framework_id=str(ops_detail.id), pays="CI")
    opening = {c: v for c, v in DETAIL_N.items() if c[0] in "12345"}
    opening["101300"] -= 35  # résultat 2026 affecté aux réserves
    tb = upload(client, rev, f["id"], "b.csv", balance_csv(DETAIL_N, opening)).json()
    assert tb["statut"] == "accepte", tb["anomalies"]
    years = client.get(
        f"/api/audit-files/{f['id']}/ops-indicators", headers=rev["aud"].headers
    ).json()
    assert [(y["exercice"], y["ratio"]) for y in years["frais_gestion"]["exercices"]] == [
        (2027, "9.50"),
        (2026, "10.00"),
    ]


def test_cip07_reserves_et_placements(client, rev, ops_detail, db):  # noqa: F811
    f = detail_file(client, rev, ops_detail)
    url = f"/api/audit-files/{f['id']}/ops-indicators"
    data = client.get(url, headers=rev["aud"].headers).json()
    assert {"reserve_technique_mois (PF)", "reserve_technique_mois (PV)", "limite_placement:IMMO"} <= set(
        data["parametres_manquants"])  # fmt: skip
    set_params(db, ops_detail, ("reserve_technique_mois", "6", "PF"), ("reserve_technique_mois", "12", "PV"),
               ("limite_placement:immo", "25", None), ("limite_placement:Oblig", "60", None))  # fmt: skip
    data = client.get(url, headers=rev["aud"].headers).json()
    assert data["parametres_manquants"] == ["plafond_frais_gestion", "limite_placement:DAT"]
    branches = {b["code"]: b for b in data["reserves"]["branches"]}
    assert set(branches) == {"PF", "PV"}  # GA ne sert pas de prestations
    assert (
        branches["PF"]["mois_couverts"],
        branches["PF"]["minimum_mois"],
        branches["PF"]["conforme"],
    ) == ("5.00", "6", False)
    assert (branches["PV"]["mois_couverts"], branches["PV"]["conforme"]) == ("18.00", True)
    placements = data["placements"]
    cats = {c["categorie"]: c for c in placements["categories"]}
    assert (cats["IMMO"]["part"], cats["IMMO"]["limite"], cats["IMMO"]["conforme"]) == (
        "30.00",
        "25",
        False,
    )
    assert (cats["OBLIG"]["part"], cats["OBLIG"]["conforme"]) == ("50.00", True)
    assert (cats["DAT"]["limite"], cats["DAT"]["conforme"]) == (None, None)
    assert (placements["total"], placements["rendement"], placements["postes_manquants"]) == (
        "100000000.00",
        "5.00",
        [],
    )


def test_cip07_postes_absents(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    data = client.get(
        f"/api/audit-files/{f['id']}/ops-indicators", headers=rev["aud"].headers
    ).json()
    assert data["reserves"] == {"postes_manquants": ["RTE", "PRE"], "branches": []}
    assert data["placements"] == {
        "postes_manquants": ["PLA_<catégorie>", "PPL"],
        "categories": [],
        "rendement": None,
    }
