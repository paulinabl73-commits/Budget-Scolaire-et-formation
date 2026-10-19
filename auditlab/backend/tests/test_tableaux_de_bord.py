"""REP-04 à REP-06 : tableaux de bord Direction, Recommandations et Mission."""

import uuid

from app.security.roles import Role
from tests import helpers
from tests.finding_helpers import team  # noqa: F401
from tests.report_helpers import validated_finding


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


def test_rep05_recommandations(client, team, db):  # noqa: F811
    import datetime as dt

    from sqlalchemy import select

    from app.models import ActionPlan, AuditableEntity, Engagement

    directeur = team["directeur"].headers
    dg = AuditableEntity(nom="Direction des achats", type="direction")
    db.add(dg)
    db.flush()
    achats = AuditableEntity(nom="Approvisionnements", type="processus", parent_id=dg.id)
    db.add(achats)
    db.flush()
    db.get(Engagement, team["mission"]["id"]).entity_id = achats.id
    db.commit()
    f1 = validated_finding(client, team, "critique", "Paiements sans pièce")
    f2 = validated_finding(client, team, "moyenne", "Retards de facturation")
    plans = {p.finding_id: p for p in db.scalars(select(ActionPlan))}
    late = plans[uuid.UUID(f1["id"])]
    late.echeance = dt.date.today() - dt.timedelta(days=30)
    done = plans[uuid.UUID(f2["id"])]
    done.statut, done.echeance = "verifie", dt.date.today() - dt.timedelta(days=5)
    db.commit()
    url = "/api/dashboards/recommendations"
    data = client.get(url, headers=directeur).json()
    assert data["constats_par_criticite"] == {"critique": 1, "elevee": 0, "moyenne": 1, "faible": 0}
    assert data["plans_par_criticite_et_statut"]["critique"]["a_lancer"] == 1
    assert data["plans_par_criticite_et_statut"]["moyenne"]["verifie"] == 1
    assert data["taux_mise_en_oeuvre"] == 50.0 and data["taux_mise_en_oeuvre_echus"] == 50.0
    assert data["retards_par_direction"] == [{"direction": "Direction des achats", "plans_en_retard": 1,
                                              "plus_ancienne_echeance": late.echeance.isoformat()}]  # fmt: skip
    row = data["plans_en_retard"][0]
    assert row["constat"] == f1["reference"] and row["jours_de_retard"] == 30
    only_moyenne = client.get(f"{url}?criticite=moyenne", headers=directeur).json()
    assert only_moyenne["plans_en_retard"] == [] and only_moyenne["taux_mise_en_oeuvre"] == 100.0
    assert client.get(f"{url}?criticite=urgente", headers=directeur).status_code == 422
