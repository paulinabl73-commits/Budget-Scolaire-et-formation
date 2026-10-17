import uuid

import pytest

from app.security.roles import Role
from tests import helpers


@pytest.fixture
def setup(client, account):
    chef = account(Role.CHEF_MISSION)
    aud = account(Role.AUDITEUR)
    other = account(Role.AUDITEUR)
    m = helpers.mission(client, chef.headers, membres=[(aud.user, "auditeur")], budget_jours=10)
    return chef, aud, other, f"/api/engagements/{m['id']}"


def _log(client, acc, url, heures, activite="terrain", date="2026-09-01", **kw):
    return client.post(
        f"{url}/time-entries",
        json={"date": date, "heures": heures, "activite": activite, **kw},
        headers=acc.headers,
    )


def test_aud08_saisie_et_comparaison_au_budget(client, setup):
    chef, aud, _, url = setup
    assert _log(client, aud, url, 8, "preparation").status_code == 201
    assert _log(client, aud, url, 7.5, commentaire="Entretiens acheteurs").status_code == 201
    assert _log(client, chef, url, 4, "revue").status_code == 201

    s = client.get(f"{url}/time-summary", headers=chef.headers).json()
    # 19,5 h / 8 h = 2,44 j sur 10 j.
    assert s["jours_consommes"] == 2.44 and s["ecart_jours"] == 7.56
    assert s["taux_consommation"] == 24.4 and s["heures_par_jour"] == 8
    assert {x["libelle"]: x["jours"] for x in s["par_personne"]} == {
        chef.user.nom: 0.5,
        aud.user.nom: 1.94,
    }
    assert {x["cle"]: x["jours"] for x in s["par_activite"]} == {
        "preparation": 1.0,
        "revue": 0.5,
        "terrain": 0.94,
    }

    mission = client.get(url, headers=chef.headers).json()
    assert mission["jours_consommes"] == 2.44
    listed = client.get("/api/engagements", headers=chef.headers).json()
    assert listed[0]["jours_consommes"] == 2.44


def test_aud08_visibilite_des_saisies(client, setup):
    chef, aud, _, url = setup
    _log(client, aud, url, 8)
    _log(client, chef, url, 2)
    assert len(client.get(f"{url}/time-entries", headers=chef.headers).json()) == 2
    own = client.get(f"{url}/time-entries", headers=aud.headers).json()
    assert [e["user_nom"] for e in own] == [aud.user.nom]


def test_aud08_correction_de_ses_saisies(client, setup):
    chef, aud, _, url = setup
    entry = _log(client, aud, url, 8).json()
    e_url = f"{url}/time-entries/{entry['id']}"
    resp = client.patch(
        e_url, json={"heures": 6, "activite": "rapport", "commentaire": None}, headers=aud.headers
    )
    assert resp.json()["heures"] == 6 and resp.json()["activite"] == "rapport"
    # Personne ne corrige les temps d'un autre, pas même le chef.
    assert client.patch(e_url, json={"heures": 1}, headers=chef.headers).status_code == 403
    assert client.delete(e_url, headers=chef.headers).status_code == 403
    assert client.delete(e_url, headers=aud.headers).status_code == 204
    assert client.get(f"{url}/time-entries", headers=aud.headers).json() == []
    assert (
        client.patch(
            f"{url}/time-entries/{uuid.uuid4()}", json={"heures": 1}, headers=aud.headers
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"heures": 0},
        {"heures": 25},
        {"heures": 1.1},
        {"date": "2999-01-01"},
        {"activite": "sieste"},
    ],
)
def test_aud08_controles(client, setup, body):
    _, aud, _, url = setup
    payload = {"date": "2026-09-01", "heures": 2, "activite": "terrain", **body}
    assert client.post(f"{url}/time-entries", json=payload, headers=aud.headers).status_code == 422


def test_aud08_reserve_a_l_equipe(client, setup, account):
    _, aud, other, url = setup
    assert _log(client, other, url, 2).status_code == 404  # mission invisible
    directeur = account(Role.DIRECTEUR)
    assert _log(client, directeur, url, 2).status_code == 403  # non membre
    entry = _log(client, aud, url, 2).json()
    resp = client.patch(
        f"{url}/time-entries/{entry['id']}", json={"date": "2999-01-01"}, headers=aud.headers
    )
    assert resp.status_code == 422
