"""CIP-02 : recalcul théorique des cotisations par employeur."""

import polars as pl

from app.models import Dataset
from tests.cipres_helpers import launch_ops, ops, ops_file, set_params  # noqa: F401
from tests.data_helpers import make_dataset
from tests.revision_helpers import create_file, rev  # noqa: F401


def tables(db, ctx):
    mission = ctx["mission"]["id"]
    decl = make_dataset(db, mission, pl.DataFrame({
        "employeur": ["E1", "E1", "E2", "E4"], "matricule": ["S1", "S2", "S3", "S4"],
        "salaire": [300_000.0, 1_500_000.0, 200_000.0, 100_000.0]}), "Déclarations")  # fmt: skip
    emissions = make_dataset(db, mission, pl.DataFrame({
        "code_employeur": ["E1", "E2", "E3"], "emis": [235_000.0, 25_000.0, 10_000.0],
        "encaisse": [200_000.0, 25_000.0, 0.0]}), "Émissions")  # fmt: skip
    return decl, emissions


def test_cip02_recalcul_des_cotisations(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    decl, emissions = tables(db, rev)
    cols = {"champ_employeur": "employeur", "champ_salaire": "salaire", "champ_employeur_emission": "code_employeur",
            "champ_emis": "emis", "champ_encaisse": "encaisse"}  # fmt: skip
    listing = client.get(
        f"/api/audit-files/{f['id']}/ops-controls", headers=rev["aud"].headers
    ).json()
    control = next(c for c in listing["controles"] if c["code"] == "cotisations")
    assert control["manquants"] == ["taux_cotisation"] and control["exigence"] == "CIP-02"
    assert "taux" not in {p["nom"] for p in control["parametres"]}
    error = launch_ops(client, rev, f, "cotisations", decl, emissions, status=409, **cols)
    assert error["detail"]["points"] == ["taux_cotisation"]
    # Taux PF 7 % et PV 8 % ; plafond général 1 000 000, aucun plafond pour les pensions.
    set_params(db, ops, ("taux_cotisation", "7", "PF"), ("taux_cotisation", "8", "PV"))
    error = launch_ops(client, rev, f, "cotisations", decl, emissions, status=409, **cols)
    assert error["detail"]["points"] == ["plafond_cotisation (PF)", "plafond_cotisation (PV)"]
    set_params(db, ops, ("plafond_cotisation", "1000000", None), ("plafond_cotisation", "0", "PV"))
    launch_ops(client, rev, f, "cotisations", decl, emissions, status=422, taux="PF=1", **cols)
    result = db.get(
        Dataset, launch_ops(client, rev, f, "cotisations", decl, emissions, **cols)["dataset_id"]
    )
    db.refresh(result)
    assert result.statut == "pret", result.erreur
    assert result.definition["controle"] == "CIP-02" and result.definition["parametres"][
        "taux"
    ] == {"PF": "7", "PV": "8"}
    assert result.resultat["par_anomalie"] == {
        "declaration_sans_emission": 1,
        "emission_sans_declaration": 1,
        "ecart_emission": 1,
    }
    page = client.post(
        f"/api/datasets/{result.id}/rows",
        json={"offset": 0, "limit": 10},
        headers=rev["aud"].headers,
    ).json()
    rows = [dict(zip(page["colonnes"], r, strict=True)) for r in page["lignes"]]
    assert [r["employeur"] for r in rows] == ["E4", "E3", "E2", "E1"]
    e1 = rows[3]
    assert (float(e1["theorique_pf"]), float(e1["theorique_pv"]), float(e1["ecart_emission"])) == (
        91_000,
        144_000,
        0,
    )
    assert e1["anomalie"] is None and float(e1["reste_a_recouvrer"]) == 35_000
    assert rows[2]["anomalie"] == "ecart_emission" and float(rows[2]["ecart_emission"]) == -5_000
    listing = client.get(
        f"/api/audit-files/{f['id']}/ops-controls", headers=rev["aud"].headers
    ).json()
    control = next(c for c in listing["controles"] if c["code"] == "cotisations")
    assert control["manquants"] == [] and control["executions"][0]["id"] == str(result.id)
    assert {(u["code"], u["branche"], u["valeur"]) for u in control["reglementaires"]} >= {
        ("plafond_cotisation", "PV", "0")
    }
    # Hors dossier CIPRES.
    other = create_file(client, rev, exercice=2025)
    assert (
        client.get(
            f"/api/audit-files/{other['id']}/ops-controls", headers=rev["aud"].headers
        ).status_code
        == 409
    )


def test_bareme_en_texte():
    from app.analytics.operations import REGISTRY, AnalysisError
    from app.analytics.operations.base import _scale

    p = next(x for x in REGISTRY["cip_cotisations"].params if x.nom == "taux")
    assert _scale("PF=7,5; PV = 8", p) == {"PF": "7.5", "PV": "8"}
    for bad in ("PF7", "P-F=1", {}, "PF=200"):
        try:
            _scale(bad, p)
        except AnalysisError:
            continue
        raise AssertionError(bad)
