"""CIP-05 : allocations familiales (âge limite, nombre d'enfants, enfant rattaché deux fois)."""

import datetime as dt

import polars as pl

from app.models import Dataset
from tests.cipres_helpers import launch_ops, ops, ops_file, set_params  # noqa: F401
from tests.data_helpers import make_dataset
from tests.revision_helpers import rev  # noqa: F401
from tests.test_cip_recouvrement import rows_of

D = dt.date


def test_cip05_allocations_familiales(client, rev, ops, db):  # noqa: F811
    f = ops_file(client, rev, ops, pays="CI")
    rows = [("A1", "K1", D(2010, 1, 1)), ("A1", "K2", D(2005, 12, 31)),  # K2 a 21 ans le 31/12/2026
            ("A1", "K3", D(2006, 1, 1)),  # 20 ans
            ("A2", "K4", D(2015, 5, 5)), ("A2", "K5", D(2016, 5, 5)), ("A2", "K6", D(2017, 5, 5)),
            ("A2", "K7", D(2018, 5, 5)), ("A3", "K1", D(2010, 1, 1))]  # fmt: skip
    df = pl.DataFrame(rows, schema=["allocataire", "enfant", "naissance"], orient="row")
    table = make_dataset(db, rev["mission"]["id"], df, "Enfants")
    cols = {
        "champ_allocataire": "allocataire",
        "champ_enfant": "enfant",
        "champ_date_naissance": "naissance",
    }
    assert launch_ops(client, rev, f, "allocations", table, status=409, **cols)["detail"]["points"] == [
        "age_limite_enfant", "nombre_enfants_maximum"]  # fmt: skip
    set_params(db, ops, ("age_limite_enfant", "21", None), ("nombre_enfants_maximum", "3", None))
    result = db.get(Dataset, launch_ops(client, rev, f, "allocations", table, **cols)["dataset_id"])
    db.refresh(result)
    assert result.statut == "pret", result.erreur
    assert result.resultat["par_critere"] == {
        "age_limite": 1,
        "nombre_anormal": 4,
        "enfant_multiple": 2,
    }
    flagged = {
        (r["allocataire"], r["enfant"]): r["criteres"] for r in rows_of(client, rev, result.id)
    }
    assert flagged[("A1", "K2")] == "age_limite" and ("A1", "K3") not in flagged
    assert flagged[("A1", "K1")] == "enfant_multiple" and flagged[("A2", "K4")] == "nombre_anormal"
    assert result.resultat["allocataires_concernes"] == 3
