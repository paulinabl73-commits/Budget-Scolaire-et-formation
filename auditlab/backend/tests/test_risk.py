from datetime import date

import pytest
from sqlalchemy import select

from app.models import AuditLog
from app.risk_scoring import CriterionSpec, compute_score, seniority_note
from app.security.roles import Role

SPECS = [
    CriterionSpec("I", "Impact", "impact", "note", 3),
    CriterionSpec("P", "Proba", "probabilite", "note", 1),
    CriterionSpec("A", "Ancienneté", "autre", "anciennete", 1),
]
ALL_HIGH = {"IMPACT_FIN": 5, "IMPACT_REG": 5, "PROBA": 5, "CTRL_INT": 5}


@pytest.mark.parametrize(
    ("last", "on", "note"),
    [
        (None, date(2027, 1, 1), 5),
        (date(2026, 6, 1), date(2027, 1, 1), 1),
        (date(2025, 6, 1), date(2027, 1, 1), 2),
        (date(2025, 1, 2), date(2027, 1, 1), 2),
        (date(2025, 1, 1), date(2027, 1, 1), 3),
        (date(2010, 1, 1), date(2027, 1, 1), 5),
        (date(2028, 1, 1), date(2027, 1, 1), 1),
    ],
)
def test_aud02_note_anciennete(last, on, note):
    assert seniority_note(last, on) == note


def test_aud02_calcul_du_score():
    r = compute_score(SPECS, {"I": 4, "P": 2}, date(2024, 1, 1), date(2027, 1, 1))
    # (3×4 + 1×2 + 1×4) / (5 × 5) × 100 = 18 / 25 = 72
    assert r.score == 72.0
    assert r.impact == 4.0 and r.probabilite == 2.0
    assert [c["note"] for c in r.criteres] == [4, 2, 4]


def test_aud02_axe_sans_critere():
    r = compute_score(SPECS[:1], {"I": 1}, None, date(2027, 1, 1))
    assert (r.score, r.impact, r.probabilite) == (20.0, 1.0, None)


@pytest.mark.parametrize(
    ("notes", "message"),
    [
        ({"I": 4}, "Note manquante"),
        ({"I": 6, "P": 1}, "hors échelle"),
        ({"I": 0, "P": 1}, "hors échelle"),
        ({"I": 1, "P": 1, "X": 2}, "inconnu"),
    ],
)
def test_aud02_notes_invalides(notes, message):
    with pytest.raises(ValueError, match=message):
        compute_score(SPECS, notes, None, date(2027, 1, 1))


def test_aud02_sans_critere():
    with pytest.raises(ValueError, match="Aucun critère"):
        compute_score([], {}, None, date(2027, 1, 1))


def _entity(client, headers, **kw):
    body = {"nom": "Achats", "type": "processus", **kw}
    return client.post("/api/universe/entities", json=body, headers=headers).json()


def test_aud02_evaluation_et_historique(client, account, criteria, db):
    h = account(Role.DIRECTEUR).headers
    e = _entity(client, h, date_dernier_audit="2023-06-30")
    url = f"/api/universe/entities/{e['id']}/assessments"

    first = client.post(
        url,
        json={
            "notes": {"IMPACT_FIN": 4, "IMPACT_REG": 3, "PROBA": 4, "CTRL_INT": 2},
            "date_evaluation": "2026-01-15",
            "commentaire": "Fraude fournisseurs signalée",
        },
        headers=h,
    )
    assert first.status_code == 201, first.text
    a = first.json()
    # Ancienneté au 15/01/2026 : 2 années pleines → note 3.
    # (3×4 + 2×3 + 3×4 + 2×2 + 1×3) / (11 × 5) × 100 = 37 / 55 = 67,3
    assert a["score"] == 67.3
    assert a["impact"] == 3.6 and a["probabilite"] == 3.2
    assert a["criteres"][-1] == {
        "code": "ANCIENNETE",
        "libelle": "Ancienneté",
        "axe": "autre",
        "mode": "anciennete",
        "poids": 1.0,
        "note": 3,
    }

    entity = client.get(f"/api/universe/entities/{e['id']}", headers=h).json()
    assert entity["score_risque"] == 67.3 and entity["impact"] == 3.6
    assert entity["date_evaluation"] == "2026-01-15"

    # Une évaluation antérieure enrichit l'historique sans écraser la plus récente.
    old = client.post(url, json={"notes": ALL_HIGH, "date_evaluation": "2025-01-01"}, headers=h)
    assert old.status_code == 201
    assert client.get(f"/api/universe/entities/{e['id']}", headers=h).json()["score_risque"] == 67.3
    history = client.get(url, headers=h).json()
    assert [x["date_evaluation"] for x in history] == ["2026-01-15", "2025-01-01"]

    log = db.scalar(select(AuditLog).where(AuditLog.object_type == "RiskAssessment"))
    assert log.action == "create" and log.apres["score"] == 67.3


def test_aud02_criteres_figes_dans_l_evaluation(client, account, criteria):
    h = account(Role.DIRECTEUR).headers
    e = _entity(client, h)
    url = f"/api/universe/entities/{e['id']}/assessments"
    client.post(url, json={"notes": ALL_HIGH}, headers=h)
    crit = client.get("/api/risk/criteria", headers=h).json()
    proba = next(c for c in crit if c["code"] == "PROBA")
    client.patch(
        f"/api/risk/criteria/{proba['id']}", json={"poids": 10, "libelle": "P2"}, headers=h
    )
    stored = client.get(url, headers=h).json()[0]["criteres"]
    assert next(c for c in stored if c["code"] == "PROBA")["poids"] == 3.0


def test_aud02_note_manquante_refusee(client, account, criteria):
    h = account(Role.DIRECTEUR).headers
    e = _entity(client, h)
    resp = client.post(
        f"/api/universe/entities/{e['id']}/assessments", json={"notes": {"PROBA": 3}}, headers=h
    )
    assert resp.status_code == 422 and "Note manquante" in resp.json()["detail"]


def test_aud02_parametrage_des_criteres(client, account, criteria):
    admin = account(Role.ADMIN).headers
    directeur = account(Role.DIRECTEUR).headers
    body = {"code": "FRAUDE", "libelle": "Exposition à la fraude", "axe": "probabilite", "poids": 2}
    created = client.post("/api/risk/criteria", json=body, headers=admin)
    assert created.status_code == 201 and created.json()["mode"] == "note"
    assert client.post("/api/risk/criteria", json=body, headers=admin).status_code == 409
    assert (
        client.post(
            "/api/risk/criteria", json={**body, "code": "minuscule"}, headers=admin
        ).status_code
        == 422
    )

    cid = created.json()["id"]
    resp = client.patch(f"/api/risk/criteria/{cid}", json={"actif": False}, headers=directeur)
    assert resp.json()["actif"] is False

    # Un critère désactivé n'est plus demandé, et sa note est refusée.
    e = _entity(client, directeur)
    url = f"/api/universe/entities/{e['id']}/assessments"
    assert client.post(url, json={"notes": ALL_HIGH}, headers=directeur).status_code == 201
    resp = client.post(url, json={"notes": {**ALL_HIGH, "FRAUDE": 3}}, headers=directeur)
    assert resp.status_code == 422
    import uuid

    assert (
        client.patch(
            f"/api/risk/criteria/{uuid.uuid4()}", json={"poids": 2}, headers=admin
        ).status_code
        == 404
    )


@pytest.mark.parametrize("role", [Role.CHEF_MISSION, Role.AUDITEUR, Role.AUDITE])
def test_aud02_droits(client, account, criteria, role):
    directeur = account(Role.DIRECTEUR).headers
    e = _entity(client, directeur)
    h = account(role).headers
    url = f"/api/universe/entities/{e['id']}/assessments"
    assert client.post(url, json={"notes": ALL_HIGH}, headers=h).status_code == 403
    assert (
        client.post(
            "/api/risk/criteria", json={"code": "X", "libelle": "X", "axe": "impact"}, headers=h
        ).status_code
        == 403
    )
    expected = 200 if role is Role.CHEF_MISSION else 403
    assert client.get(url, headers=h).status_code == expected
    assert client.get("/api/risk/criteria", headers=h).status_code == expected


@pytest.mark.parametrize(("value", "cell"), [(1.0, 1), (2.49, 2), (2.5, 3), (3.6, 4), (5.0, 5)])
def test_aud03_case_de_la_carte(value, cell):
    from app.risk_scoring import map_cell

    assert map_cell(value) == cell


def test_aud03_carte_des_risques(client, account, criteria):
    h = account(Role.DIRECTEUR).headers
    a = _entity(client, h, nom="Achats")
    b = _entity(client, h, nom="Paie")
    _entity(client, h, nom="Trésorerie")
    client.post(
        f"/api/universe/entities/{a['id']}/assessments", json={"notes": ALL_HIGH}, headers=h
    )
    client.post(
        f"/api/universe/entities/{b['id']}/assessments",
        json={"notes": {"IMPACT_FIN": 4, "IMPACT_REG": 3, "PROBA": 2, "CTRL_INT": 2}},
        headers=h,
    )

    carte = client.get("/api/risk/map", headers=account(Role.CHEF_MISSION).headers).json()
    assert carte["echelle"] == 5 and len(carte["cellules"]) == 25
    filled = {
        (c["impact"], c["probabilite"]): [e["nom"] for e in c["entites"]]
        for c in carte["cellules"]
        if c["entites"]
    }
    # Paie : impact (3×4 + 2×3) / 5 = 3,6 → 4 ; probabilité 2.
    assert filled == {(5, 5): ["Achats"], (4, 2): ["Paie"]}
    assert [e["nom"] for e in carte["non_evaluees"]] == ["Trésorerie"]


def test_aud03_carte_refusee(client, account):
    assert client.get("/api/risk/map", headers=account(Role.AUDITEUR).headers).status_code == 403
