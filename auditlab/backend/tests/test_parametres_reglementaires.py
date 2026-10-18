"""CIP-09 : seuils, taux, plafonds et limites paramétrés par pays et par exercice."""

from decimal import Decimal

import pytest

from app.revision.frameworks import builtin, load_framework
from app.revision.parameters import MissingParameters, resolve, values
from app.security.roles import Role


def test_cip09_parametres(client, db, account):
    fw = load_framework(db, builtin("cipres_modele"))
    db.commit()
    admin, chef = account(Role.ADMIN).headers, account(Role.CHEF_MISSION).headers
    url = f"/api/frameworks/{fw.id}/parameters"
    listing = client.get(url, headers=chef).json()
    assert {p["code"] for p in listing["catalogue"]} >= {"taux_cotisation", "plafond_frais_gestion"}
    assert listing["parametres"] == []  # aucune valeur livrée
    body = {
        "code": "taux_cotisation",
        "libelle": "Taux PF",
        "valeur": "7",
        "unite": "%",
        "pays": "CI",
        "exercice": 2024,
        "branche": "PF",
    }
    assert client.post(url, json=body, headers=chef).status_code == 403
    assert client.post(url, json={**body, "branche": "XX"}, headers=admin).status_code == 422
    assert client.post(url, json=body, headers=admin).status_code == 201
    assert client.post(url, json=body, headers=admin).status_code == 409
    client.post(url, json={**body, "valeur": "8", "exercice": 2026}, headers=admin)
    client.post(url, json={**body, "valeur": "6", "pays": None, "exercice": None}, headers=admin)
    generic_gm = client.post(
        url,
        json={"code": "plafond_frais_gestion", "libelle": "Plafond", "valeur": "15"},
        headers=admin,
    ).json()
    # Le plus précis l'emporte ; un paramètre vaut jusqu'à son remplacement.
    assert resolve(db, fw.id, "taux_cotisation", "CI", 2026, "PF").valeur == Decimal(8)
    assert resolve(db, fw.id, "taux_cotisation", "CI", 2025, "PF").valeur == Decimal(7)
    assert resolve(db, fw.id, "taux_cotisation", "CI", 2023, "PF").valeur == Decimal(
        6
    )  # repli sans pays
    assert resolve(db, fw.id, "taux_cotisation", "SN", 2026, "PF").valeur == Decimal(6)
    assert resolve(db, fw.id, "taux_cotisation", "CI", 2026, "RP") is None
    got = values(
        db, fw.id, "CI", 2026, [("taux_cotisation", "PF"), ("plafond_frais_gestion", None)]
    )
    assert got == {
        ("taux_cotisation", "PF"): Decimal(8),
        ("plafond_frais_gestion", None): Decimal(15),
    }
    with pytest.raises(MissingParameters) as exc:
        values(db, fw.id, "CI", 2026, [("taux_cotisation", "RP"), ("age_limite_enfant", None)])
    assert exc.value.missing == ["taux_cotisation (RP)", "age_limite_enfant"]
    assert (
        client.delete(f"/api/regulatory-parameters/{generic_gm['id']}", headers=admin).status_code
        == 204
    )
    assert resolve(db, fw.id, "plafond_frais_gestion", "CI", 2026) is None
