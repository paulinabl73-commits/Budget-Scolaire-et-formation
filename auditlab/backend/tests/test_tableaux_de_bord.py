"""REP-04 à REP-06 : tableaux de bord Direction, Recommandations et Mission."""

from app.security.roles import Role
from tests import helpers


def _log(client, acc, url, heures, date="2026-01-10"):
    resp = client.post(f"{url}/time-entries", json={"date": date, "heures": heures,
                       "activite": "terrain"}, headers=acc.headers)  # fmt: skip
    assert resp.status_code == 201, resp.text


def test_rep04_direction(client, account, db):
    directeur, chef = account(Role.DIRECTEUR), account(Role.CHEF_MISSION)
    dg = helpers.entity(client, directeur.headers, "Direction financière", type="direction")
    achats = helpers.entity(client, directeur.headers, "Achats", parent_id=dg["id"])
    paie = helpers.entity(client, directeur.headers, "Paie")
    plan, items = helpers.validated_plan(client, directeur.headers, [achats, paie], annee=2026)
    m1 = helpers.mission(client, chef.headers, titre="Audit achats", entity_id=achats["id"],
                         plan_item_id=items[0]["id"], date_debut="2026-01-04",
                         date_fin="2026-02-26", budget_jours=20)  # fmt: skip
    helpers.mission(client, chef.headers, titre="Audit paie", entity_id=paie["id"],
                         date_debut="2026-06-01", date_fin="2026-06-30", budget_jours=10)  # fmt: skip
    for day in ("2026-01-11", "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15"):
        _log(client, chef, f"/api/engagements/{m1['id']}", 8, day)  # 5 jours
    from app.models import Engagement

    db.get(Engagement, m1["id"]).statut = "cloturee"
    db.commit()
    url = "/api/dashboards/direction"
    assert client.get(url, headers=chef.headers).status_code == 403
    data = client.get(url, headers=directeur.headers).json()
    assert data["plan"] == {"annee": 2026, "version": 1, "missions_prevues": 2, "missions_lancees": 1,
                            "missions_cloturees": 1, "taux_realisation": 50.0, "budget_jours": 41}  # fmt: skip
    assert (
        data["missions_par_statut"]["cloturee"] == 1
        and data["missions_par_statut"]["planifiee"] == 1
    )
    assert (data["budget_jours"], data["jours_consommes"], data["taux_consommation"]) == (
        30,
        5.0,
        16.7,
    )
    row = next(m for m in data["missions"] if m["id"] == m1["id"])
    assert row["ecart_jours"] == 15.0 and row["entite"] == "Achats"
    # Filtres : entité (avec ses descendants) et période.
    by_entity = client.get(f"{url}?entity_id={dg['id']}", headers=directeur.headers).json()
    assert [m["titre"] for m in by_entity["missions"]] == ["Audit achats"]
    assert by_entity["plan"]["missions_prevues"] == 1
    by_period = client.get(
        f"{url}?debut=2026-05-01&fin=2026-12-31", headers=directeur.headers
    ).json()
    assert [m["titre"] for m in by_period["missions"]] == ["Audit paie"]
    assert (
        client.get(f"{url}?debut=2026-05-01&fin=2026-01-01", headers=directeur.headers).status_code
        == 422
    )
