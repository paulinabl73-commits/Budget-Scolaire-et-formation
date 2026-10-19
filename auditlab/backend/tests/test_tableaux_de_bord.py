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


def test_rep06_mission(client, team, account):  # noqa: F811
    from app.richtext import from_plain_text

    chef, aud = team["chef"], team["aud"]
    wp2 = client.post(f"{team['url']}/workpapers", headers=aud.headers, json={
        "reference": "A-2", "titre": "Factures", "travaux": from_plain_text("Tests"),
        "conclusion": "Satisfaisant", "evaluation": "efficace"}).json()  # fmt: skip
    for acc, kind in ((aud, "prepare"), (chef, "revu"), (chef, "approuve")):
        resp = client.post(
            f"/api/workpapers/{wp2['id']}/signoffs", json={"type": kind}, headers=acc.headers
        )
        assert resp.status_code == 201, resp.text
    client.post(f"/api/workpapers/{team['wp']['id']}/review-notes", headers=chef.headers,
                json={"texte": "Compléter", "ancre": {"champ": "travaux", "citation": "x"}})  # fmt: skip
    _log(client, aud, team["url"], 8, "2026-09-01")
    _log(client, chef, team["url"], 4, "2026-09-02")
    url = f"/api/dashboards/missions/{team['mission']['id']}"
    data = client.get(url, headers=aud.headers).json()
    assert data["papiers"]["par_etat"] == {"brouillon": 1, "prepare": 0, "revu": 0, "approuve": 1}
    assert data["papiers"]["taux_approbation"] == 50.0 and data["notes_ouvertes"] == 1
    assert (
        next(w for w in data["papiers"]["liste"] if w["reference"] == "A-1")["notes_ouvertes"] == 1
    )
    assert data["temps"]["jours_consommes"] == 1.5
    assert {p["nom"]: p["jours"] for p in data["temps"]["par_personne"]} == {
        aud.user.nom: 1.0,
        chef.user.nom: 0.5,
    }
    assert data["temps"]["par_activite"] == [{"activite": "terrain", "jours": 1.5}]
    assert client.get(url, headers=account(Role.AUDITEUR).headers).status_code == 404


def test_rep07_comite(client, team, db):  # noqa: F811
    import datetime as dt
    import io

    from docx import Document

    from app.models import Engagement

    f = validated_finding(client, team, "critique", "Paiements sans pièce")
    engagement = db.get(Engagement, team["mission"]["id"])
    engagement.statut, engagement.cloturee_le = "cloturee", dt.datetime.now(dt.UTC)
    db.commit()
    quarter = (dt.date.today().month - 1) // 3 + 1
    url = f"/api/dashboards/committee?annee={dt.date.today().year}&trimestre={quarter}"
    assert client.get(url, headers=team["chef"].headers).status_code == 403
    assert client.get(f"{url[:-1]}5", headers=team["directeur"].headers).status_code == 422
    pdf = client.get(url, headers=team["directeur"].headers)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    docx = client.get(f"{url}&format=docx", headers=team["directeur"].headers)
    doc = Document(io.BytesIO(docx.content))
    text = "\n".join(
        [p.text for p in doc.paragraphs]
        + [c.text for t in doc.tables for r in t.rows for c in r.cells]
    )
    for expected in ("Rapport au comité d'audit", f"T{quarter}", "1 mission(s) clôturée(s)",
                     "1 constat(s) validé(s), dont 1 de criticité élevée", f"{f['reference']} – Paiements sans pièce",
                     "Taux de mise en œuvre", "6. Ressources"):  # fmt: skip
        assert expected in text, expected


def test_rep07_trimestres():
    import datetime as dt

    from app.reporting.committee import bounds

    assert bounds(2026, 1) == (dt.date(2026, 1, 1), dt.date(2026, 3, 31))
    assert bounds(2026, 4) == (dt.date(2026, 10, 1), dt.date(2026, 12, 31))


def test_rep08_exports_excel(client, team, db):  # noqa: F811
    import io

    from openpyxl import load_workbook

    validated_finding(client, team, "critique", "Paiements sans pièce")
    directeur = team["directeur"].headers
    for path, sheets in (
        ("direction/export?debut=2026-01-01", ["Filtres", "Synthèse", "Missions par statut", "Missions"]),
        ("recommendations/export?criticite=critique",
         ["Filtres", "Synthèse", "Criticité et statut", "Retards par direction", "Plans en retard"]),
        (f"missions/{team['mission']['id']}/export",
         ["Filtres", "Synthèse", "Papiers de travail", "Temps par personne", "Temps par activité"]),
    ):  # fmt: skip
        resp = client.get(f"/api/dashboards/{path}", headers=directeur)
        assert resp.status_code == 200, path
        wb = load_workbook(io.BytesIO(resp.content))
        assert wb.sheetnames == sheets
    wb = load_workbook(io.BytesIO(client.get("/api/dashboards/recommendations/export?criticite=critique",
                                             headers=directeur).content))  # fmt: skip
    assert ["Criticité", "critique"] in [[c.value for c in r] for r in wb["Filtres"].iter_rows()]
    rows = [[c.value for c in r] for r in wb["Criticité et statut"].iter_rows()]
    assert rows[1][:3] == ["critique", 1, 1]  # constat critique, un plan « à lancer »
    assert (
        client.get("/api/dashboards/direction/export", headers=team["chef"].headers).status_code
        == 403
    )
