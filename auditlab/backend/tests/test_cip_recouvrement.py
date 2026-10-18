"""CIP-03 : recouvrement (déclarations manquantes ou tardives, majorations, créances anciennes)."""

import datetime as dt

import polars as pl

from app.models import Dataset
from tests.cipres_helpers import launch_ops, ops, ops_file, set_params  # noqa: F401
from tests.data_helpers import make_dataset
from tests.revision_helpers import rev  # noqa: F401

D = dt.date


def rows_of(client, ctx, result_id):
    page = client.post(
        f"/api/datasets/{result_id}/rows",
        json={"offset": 0, "limit": 50},
        headers=ctx["aud"].headers,
    ).json()
    return [dict(zip(page["colonnes"], r, strict=True)) for r in page["lignes"]]


def declarations(db, ctx):
    rows = [
        ("E1", D(2026, m, 1), D(2026, m + 1, 10), 100_000.0, 0.0)
        for m in range(1, 12)
        if m not in (3, 6)
    ]
    rows += [("E1", D(2026, 12, 1), D(2027, 1, 10), 100_000.0, 0.0),
             ("E1", D(2026, 6, 1), D(2026, 8, 20), 100_000.0, 1_000.0),  # 36 jours de retard
             ("E2", D(2026, 11, 1), D(2026, 12, 5), 80_000.0, 0.0),
             ("E3", D(2026, 1, 1), D(2026, 2, 28), 50_000.0, 500.0),  # 13 jours de retard
             ("E9", D(2026, 5, 1), D(2026, 6, 5), 10_000.0, 0.0)]  # fmt: skip
    df = pl.DataFrame(
        rows, schema=["employeur", "periode", "depot", "cotisations", "majoration"], orient="row"
    )
    registry = pl.DataFrame({"numero": ["E1", "E2", "E3"], "affiliation": [D(2020, 1, 1), D(2026, 11, 15), D(2019, 5, 1)],
                             "cessation": [None, None, D(2026, 1, 31)]})  # fmt: skip
    mission = ctx["mission"]["id"]
    return make_dataset(db, mission, df, "Déclarations"), make_dataset(
        db, mission, registry, "Registre"
    )


def test_cip03_declarations_et_majorations(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    decl, registry = declarations(db, rev)
    cols = {"champ_employeur": "employeur", "champ_periode": "periode", "champ_date_depot": "depot",
            "champ_cotisations": "cotisations", "champ_majoration": "majoration",
            "champ_employeur_registre": "numero", "champ_date_affiliation": "affiliation",
            "champ_date_cessation": "cessation"}  # fmt: skip
    error = launch_ops(client, rev, f, "recouvrement", decl, registry, status=409, **cols)
    assert error["detail"]["points"] == [
        "delai_declaration_jours",
        "taux_majoration_retard",
        "majoration_par_mois_retard",
    ]
    set_params(db, ops, ("delai_declaration_jours", "15", None), ("taux_majoration_retard", "1", None),
               ("majoration_par_mois_retard", "1", None))  # fmt: skip
    launch_ops(
        client, rev, f, "recouvrement", decl, registry, status=422, debut="2026-02-01", **cols
    )
    result = db.get(
        Dataset, launch_ops(client, rev, f, "recouvrement", decl, registry, **cols)["dataset_id"]
    )
    db.refresh(result)
    assert result.statut == "pret", result.erreur
    assert result.definition["parametres"]["debut"] == "2026-01-01"
    assert result.resultat["par_anomalie"] == {"declaration_tardive": 2, "non_declarant": 2,
                                               "majoration_non_appliquee": 1, "non_immatricule": 1}  # fmt: skip
    rows = rows_of(client, rev, result.id)
    found = {(r["anomalie"], r["employeur"], r["periode"]) for r in rows}
    assert {("non_declarant", "E1", "2026-03-01"), ("non_declarant", "E2", "2026-12-01"),
            ("non_immatricule", "E9", None)} <= found  # fmt: skip
    late = {r["employeur"]: r for r in rows if r["anomalie"] == "declaration_tardive"}
    assert (
        late["E1"]["jours_retard"] == 36 and float(late["E1"]["majoration_due"]) == 2_000
    )  # deux mois entamés
    assert late["E3"]["jours_retard"] == 13 and float(late["E3"]["majoration_due"]) == 500
    missing = next(r for r in rows if r["anomalie"] == "majoration_non_appliquee")
    assert (missing["employeur"], float(missing["majoration_appliquee"])) == ("E1", 1_000)


def test_cip03_majoration_forfaitaire_sans_colonne_majoration(client, rev, ops, db):  # noqa: F811
    from app.analytics.operations import REGISTRY
    from app.analytics.relation import relation

    decl, registry = declarations(db, rev)
    p = {"champ_employeur": "employeur", "champ_periode": "periode", "champ_date_depot": "depot",
         "champ_cotisations": "cotisations", "champ_employeur_registre": "numero", "debut": "2026-01-01",
         "fin": "2026-12-31", "periodicite": "trimestrielle", "delai_jours": 15, "taux_majoration": "10",
         "par_mois": 0, "tolerance": "0"}  # fmt: skip
    out = REGISTRY["cip_recouvrement"].run([relation(db, decl), relation(db, registry)], p)
    assert out.resultat["criteres_non_appliques"] == ["majoration_non_appliquee"]
    late = out.df.filter(pl.col("anomalie") == "declaration_tardive")
    # En trimestriel, seule la déclaration de juin dépasse le 15 juillet ; majoration forfaitaire 10 %.
    assert late["employeur"].to_list() == ["E1"] and float(late["majoration_due"][0]) == 10_000
    # Sans dates d'affiliation, tous les employeurs du registre sont attendus chaque trimestre.
    gaps = out.df.filter(pl.col("anomalie") == "non_declarant")
    assert sorted(set(gaps["employeur"])) == ["E2", "E3"]


def test_cip03_creances_anciennes(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    df = pl.DataFrame({"cotisant": ["E1", "E2", "E3", "E4"], "montant": [1_000_000.0, 500_000.0, 200_000.0, 300_000.0],
                       "exigible": [D(2025, 6, 30), D(2026, 10, 31), D(2025, 1, 31), D(2025, 12, 31)],
                       "depreciation": [None, 0.0, 200_000.0, 100_000.0]})  # fmt: skip
    table = make_dataset(db, rev["mission"]["id"], df, "Créances")
    cols = {
        "champ_montant": "montant",
        "champ_date_exigibilite": "exigible",
        "champ_depreciation": "depreciation",
    }
    assert launch_ops(client, rev, f, "creances", table, status=409, **cols)["detail"]["points"] == [
        "anciennete_depreciation_creances_mois", "taux_depreciation_creances"]  # fmt: skip
    set_params(
        db,
        ops,
        ("anciennete_depreciation_creances_mois", "12", None),
        ("taux_depreciation_creances", "100", None),
    )
    result = db.get(Dataset, launch_ops(client, rev, f, "creances", table, **cols)["dataset_id"])
    db.refresh(result)
    assert result.statut == "pret", result.erreur
    assert result.resultat == {
        "creances_retenues": 2,
        "insuffisance_totale": "1200000.00",
        "creances_source": 4,
    }
    rows = rows_of(client, rev, result.id)
    assert [(r["cotisant"], float(r["insuffisance"])) for r in rows] == [
        ("E1", 1_000_000),
        ("E4", 200_000),
    ]
