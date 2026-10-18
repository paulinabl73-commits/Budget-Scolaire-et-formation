"""CIP-04 : contrôles du fichier des bénéficiaires de prestations et de pensions."""

import datetime as dt

import polars as pl

from app.models import Dataset
from tests.cipres_helpers import launch_ops, ops, ops_file, set_params  # noqa: F401
from tests.data_helpers import make_dataset
from tests.revision_helpers import rev  # noqa: F401
from tests.test_cip_recouvrement import rows_of

D = dt.date
COLUMNS = ["id", "nom", "naissance", "rib", "deces", "dernier_paiement", "certificat", "montant"]
PENSIONERS = [
    ("P1", "KOUASSI Yao", D(1955, 3, 1), "CI001", None, D(2026, 12, 31), D(2026, 6, 30), 150_000.0),  # conforme
    ("P2", "Koffi Amenan", D(1950, 1, 1), "CI002", None, D(2026, 12, 31), D(2026, 9, 1), 120_000.0),
    ("P2", "Koffi Amenan", D(1950, 1, 1), "CI003", None, D(2026, 12, 31), D(2026, 9, 1), 120_000.0),  # même identifiant
    ("P3", "Traoré Moussa", D(1948, 7, 14), "CI004", None, D(2026, 12, 31), D(2026, 10, 1), 90_000.0),
    ("P4", "TRAORE Mousa", D(1948, 7, 14), "CI005", None, D(2026, 12, 31), D(2026, 10, 1), 90_000.0),  # nom proche
    ("P5", "Diallo Awa", D(1952, 2, 2), "CI006", None, D(2026, 12, 31), D(2026, 11, 1), 100_000.0),
    ("P6", "Bamba Issa", D(1953, 4, 4), "CI006", None, D(2026, 12, 31), D(2026, 11, 1), 100_000.0),  # même compte
    ("P7", "Yao Akissi", D(1900, 1, 1), "CI007", None, D(2026, 12, 31), D(2026, 11, 1), 100_000.0),  # 126 ans
    ("P8", "Gbagbo Lia", D(1949, 5, 5), "CI008", D(2026, 3, 31), D(2026, 12, 31), D(2026, 1, 15), 100_000.0),  # décédé
    ("P9", "Ouattara Ali", D(1951, 6, 6), "CI009", None, D(2026, 12, 31), D(2025, 5, 31), 100_000.0),  # certificat périmé
    ("P10", "Konan Ehui", D(1954, 8, 8), "CI010", None, D(2026, 12, 31), D(2026, 11, 1), 900_000.0),  # hors barème
]  # fmt: skip


def test_cip04_prestations_et_pensions(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    table = make_dataset(
        db,
        rev["mission"]["id"],
        pl.DataFrame(PENSIONERS, schema=COLUMNS, orient="row"),
        "Pensionnés",
    )
    cols = {"champ_identifiant": "id", "champ_nom": "nom", "champ_date_naissance": "naissance", "champ_compte_bancaire": "rib",
            "champ_date_deces": "deces", "champ_dernier_paiement": "dernier_paiement", "champ_certificat_vie": "certificat",
            "champ_montant": "montant"}  # fmt: skip
    assert (
        len(
            launch_ops(client, rev, f, "prestations", table, status=409, **cols)["detail"]["points"]
        )
        == 5
    )
    set_params(db, ops, ("age_minimum_pension", "55", None), ("age_maximum_beneficiaire", "110", None),
               ("validite_certificat_vie_mois", "12", None), ("pension_minimum", "50000", None),
               ("pension_maximum", "500000", None))  # fmt: skip
    result = db.get(Dataset, launch_ops(client, rev, f, "prestations", table, **cols)["dataset_id"])
    db.refresh(result)
    assert result.statut == "pret", result.erreur
    assert (
        result.resultat["criteres_non_appliques"] == [] and result.resultat["lignes_source"] == 11
    )
    assert result.resultat["par_critere"] == {"doublon_identifiant": 2, "nom_proche": 2, "meme_compte": 2, "age_anormal": 1,
                                              "paye_apres_deces": 1, "certificat_vie": 1, "hors_bareme": 1}  # fmt: skip
    flagged = {r["id"]: r["criteres"] for r in rows_of(client, rev, result.id)}
    assert (
        "P1" not in flagged
        and flagged["P4"] == "nom_proche"
        and flagged["P8"] == "paye_apres_deces"
    )
    assert (
        flagged["P7"] == "age_anormal"
        and flagged["P9"] == "certificat_vie"
        and flagged["P10"] == "hors_bareme"
    )
    # Sans date de naissance ni compte : critères correspondants non appliqués.
    few = {"champ_identifiant": "id", "champ_nom": "nom"}
    minimal = db.get(Dataset, launch_ops(client, rev, f, "prestations", table, **few)["dataset_id"])
    db.refresh(minimal)
    assert minimal.resultat["criteres_non_appliques"] == ["nom_proche", "meme_compte", "age_anormal", "paye_apres_deces",
                                                           "certificat_vie", "hors_bareme"]  # fmt: skip
    assert minimal.resultat["lignes_retenues"] == 2
