"""RCO-22 : taux, barèmes et règles fiscales par pays et par exercice, jamais dans le code."""

import pytest
from fastapi import HTTPException

from tests.portfolio_helpers import cabinet  # noqa: F401


def test_rco22_parametres_fiscaux(client, cabinet, db):  # noqa: F811
    from app.cabinet.fiscal import resolve, values

    expert, collab = cabinet["expert"], cabinet["collab"]
    listing = client.get("/api/fiscal-parameters", headers=collab.headers).json()
    assert {"taux_is", "taux_tva_normal", "taux_impot_minimum"} <= {
        c["code"] for c in listing["catalogue"]
    }
    assert listing["parametres"] == []  # aucune valeur livrée
    url = "/api/fiscal-parameters"
    for exercice, taux in ((None, "25"), (2026, "27.5")):
        body = {"pays": "CI", "code": "taux_is", "valeur": taux, "exercice": exercice}
        assert client.post(url, json=body, headers=expert.headers).status_code == 201
    assert (
        client.post(
            url, json={"pays": "CI", "code": "taux_is", "valeur": "1"}, headers=expert.headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            url, json={"pays": "CI", "code": "inconnu", "valeur": "1"}, headers=expert.headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            url, json={"pays": "SN", "code": "taux_is", "valeur": "30"}, headers=collab.headers
        ).status_code
        == 403
    )
    assert (
        resolve(db, "CI", 2025, "taux_is").valeur == 25
        and resolve(db, "CI", 2027, "taux_is").valeur == 27.5
    )
    assert resolve(db, "SN", 2026, "taux_is") is None
    with pytest.raises(HTTPException) as exc:
        values(db, "CI", 2026, ["taux_is", "taux_tva_normal"])
    assert exc.value.detail["points"] == ["taux_tva_normal"]
    data = client.get(f"{url}?pays=CI", headers=collab.headers).json()["parametres"]
    assert [(p["exercice"], p["valeur"]) for p in data] == [(2026, "27.5"), (None, "25")]
    assert client.delete(f"{url}/{data[0]['id']}", headers=expert.headers).status_code == 204
