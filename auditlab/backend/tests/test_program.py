import uuid

import pytest

from app.security.roles import Role
from tests import helpers

RISK = {"libelle": "Fournisseurs fictifs", "cycle": "achats", "categorie": "fraude"}
CONTROL = {
    "libelle": "Validation des créations de fournisseurs",
    "cycle": "achats",
    "type_controle": "preventif",
    "nature": "manuel",
    "frequence": "ponctuel",
}


@pytest.fixture
def library(client, account):
    """Un risque de bibliothèque couvert par deux contrôles, dont un avec deux procédures."""
    chef = account(Role.CHEF_MISSION)
    h = chef.headers
    risk = client.post("/api/library/risks", json=RISK, headers=h).json()
    c1 = client.post("/api/library/controls", json=CONTROL, headers=h).json()
    c2 = client.post(
        "/api/library/controls",
        json={**CONTROL, "libelle": "Rapprochement à trois voies"},
        headers=h,
    ).json()
    client.put(
        f"/api/library/risks/{risk['id']}/controls",
        json={"control_ids": [c1["id"], c2["id"]]},
        headers=h,
    )
    for d, t in (
        ("Revue des créations sur échantillon", "efficacite"),
        ("Walk-through du circuit", "conception"),
    ):
        resp = client.post(
            "/api/library/procedures",
            json={"control_id": c1["id"], "description": d, "type_test": t},
            headers=h,
        )
        assert resp.status_code == 201
    return chef, risk, c1, c2


def test_aud11_import_depuis_la_bibliotheque(client, account, library, db):
    chef, risk, c1, c2 = library
    aud = account(Role.AUDITEUR)
    m = helpers.mission(client, chef.headers, membres=[(aud.user, "auditeur")])
    url = f"/api/engagements/{m['id']}"

    resp = client.post(f"{url}/risks", json={"library_risk_id": risk["id"]}, headers=chef.headers)
    assert resp.status_code == 201
    copied = resp.json()
    assert copied["source_id"] == risk["id"] and copied["id"] != risk["id"]
    assert sorted(c["libelle"] for c in copied["controles"]) == sorted(
        [c1["libelle"], c2["libelle"]]
    )
    procs = next(c for c in copied["controles"] if c["source_id"] == c1["id"])["procedures"]
    assert [(p["reference"], p["type_test"]) for p in procs] == [
        ("P-01", "efficacite"),
        ("P-02", "conception"),
    ]

    # Un contrôle de bibliothèque n'est copié qu'une fois par mission.
    resp = client.post(
        f"{url}/controls",
        json={"library_control_id": c1["id"], "risk_ids": [copied["id"]]},
        headers=chef.headers,
    )
    assert resp.status_code == 201
    matrix = client.get(f"{url}/matrix", headers=aud.headers).json()
    assert len(matrix["risques"]) == 1 and len(matrix["controles"]) == 2

    # La bibliothèque reste intacte quand la mission modifie sa copie.
    resp = client.patch(
        f"{url}/risks/{copied['id']}",
        json={"libelle": "Fournisseurs fictifs (Sage)"},
        headers=chef.headers,
    )
    assert resp.json()["libelle"] == "Fournisseurs fictifs (Sage)"
    assert (
        client.get("/api/library/risks", headers=chef.headers).json()[0]["libelle"]
        == RISK["libelle"]
    )


def test_aud11_matrice_propre_a_la_mission(client, library):
    chef = library[0]
    m = helpers.mission(client, chef.headers)
    url = f"/api/engagements/{m['id']}"
    r = client.post(
        f"{url}/risks",
        json={"libelle": "Contournement du workflow", "cycle": "achats", "categorie": "conformite"},
        headers=chef.headers,
    ).json()
    c = client.post(
        f"{url}/controls",
        json={**CONTROL, "libelle": "Revue des accès ERP", "risk_ids": [r["id"]]},
        headers=chef.headers,
    ).json()
    p = client.post(
        f"{url}/procedures",
        json={
            "control_id": c["id"],
            "type_test": "efficacite",
            "description": "Extraire les droits",
        },
        headers=chef.headers,
    )
    assert p.status_code == 201 and p.json()["reference"] == "P-01"
    pid = p.json()["id"]
    resp = client.patch(
        f"{url}/procedures/{pid}",
        json={"description": "Extraire et revoir les droits"},
        headers=chef.headers,
    )
    assert resp.json()["description"] == "Extraire et revoir les droits"

    other = client.post(
        f"{url}/controls", json={**CONTROL, "libelle": "Second"}, headers=chef.headers
    ).json()
    resp = client.put(
        f"{url}/risks/{r['id']}/controls", json={"control_ids": [other["id"]]}, headers=chef.headers
    )
    assert [x["libelle"] for x in resp.json()["controles"]] == ["Second"]
    resp = client.patch(
        f"{url}/controls/{other['id']}", json={"nature": "automatique"}, headers=chef.headers
    )
    assert resp.json()["nature"] == "automatique"

    assert client.delete(f"{url}/procedures/{pid}", headers=chef.headers).status_code == 204
    assert client.delete(f"{url}/controls/{c['id']}", headers=chef.headers).status_code == 204
    assert client.delete(f"{url}/risks/{r['id']}", headers=chef.headers).status_code == 204
    matrix = client.get(f"{url}/matrix", headers=chef.headers).json()
    assert matrix["risques"] == [] and [x["libelle"] for x in matrix["controles"]] == ["Second"]
    # La numérotation des procédures ne réutilise pas un numéro supprimé.
    p2 = client.post(
        f"{url}/procedures",
        json={"control_id": other["id"], "type_test": "substantif", "description": "Test"},
        headers=chef.headers,
    )
    assert p2.json()["reference"] == "P-02"


def test_aud11_controles(client, library):
    chef = library[0]
    m = helpers.mission(client, chef.headers)
    other = helpers.mission(client, chef.headers)
    url = f"/api/engagements/{m['id']}"
    assert (
        client.post(f"{url}/risks", json={"libelle": "X"}, headers=chef.headers).status_code == 422
    )
    assert (
        client.post(f"{url}/controls", json={"libelle": "X"}, headers=chef.headers).status_code
        == 422
    )
    assert (
        client.post(
            f"{url}/risks", json={"library_risk_id": str(uuid.uuid4())}, headers=chef.headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{url}/controls", json={"library_control_id": str(uuid.uuid4())}, headers=chef.headers
        ).status_code
        == 404
    )
    # Un contrôle d'une autre mission ne peut pas être rattaché.
    foreign = client.post(
        f"/api/engagements/{other['id']}/controls", json=CONTROL, headers=chef.headers
    ).json()
    r = client.post(f"{url}/risks", json=RISK, headers=chef.headers).json()
    resp = client.put(
        f"{url}/risks/{r['id']}/controls",
        json={"control_ids": [foreign["id"]]},
        headers=chef.headers,
    )
    assert resp.status_code == 404
    resp = client.post(
        f"{url}/procedures",
        json={"control_id": foreign["id"], "type_test": "substantif", "description": "x"},
        headers=chef.headers,
    )
    assert resp.status_code == 404
    for path in ("risks", "controls", "procedures"):
        assert (
            client.delete(f"{url}/{path}/{uuid.uuid4()}", headers=chef.headers).status_code == 404
        )


def test_aud11_droits_et_cloture(client, account, library, db):
    chef = library[0]
    aud = account(Role.AUDITEUR)
    m = helpers.mission(client, chef.headers, membres=[(aud.user, "auditeur")])
    url = f"/api/engagements/{m['id']}"
    assert client.post(f"{url}/risks", json=RISK, headers=aud.headers).status_code == 403
    assert client.get(f"{url}/matrix", headers=aud.headers).status_code == 200
    helpers.diffused_report(db, m["id"])  # REP-03
    for statut in ("preparation", "terrain", "revue", "rapport", "cloturee"):
        client.post(f"{url}/status", json={"statut": statut}, headers=chef.headers)
    assert client.post(f"{url}/risks", json=RISK, headers=chef.headers).status_code == 409


def test_aud11_procedures_de_bibliotheque(client, library):
    chef, _, c1, _ = library
    controls = client.get("/api/library/controls", headers=chef.headers).json()
    procs = next(c for c in controls if c["id"] == c1["id"])["procedures"]
    assert len(procs) == 2
    resp = client.patch(
        f"/api/library/procedures/{procs[0]['id']}",
        json={"type_test": "substantif"},
        headers=chef.headers,
    )
    assert resp.json()["type_test"] == "substantif"
    assert (
        client.delete(f"/api/library/procedures/{procs[0]['id']}", headers=chef.headers).status_code
        == 204
    )
    assert (
        client.patch(
            f"/api/library/procedures/{procs[0]['id']}",
            json={"type_test": "substantif"},
            headers=chef.headers,
        ).status_code
        == 404
    )


def test_aud12_affectation_et_avancement(client, account, library):
    chef = library[0]
    aud = account(Role.AUDITEUR)
    aud2 = account(Role.AUDITEUR)
    m = helpers.mission(
        client,
        chef.headers,
        membres=[(aud.user, "auditeur")],
        date_debut="2026-01-01",
        date_fin="2027-12-31",
    )
    url = f"/api/engagements/{m['id']}"
    risk = client.post(
        f"{url}/risks", json={"library_risk_id": library[1]["id"]}, headers=chef.headers
    ).json()
    proc = next(c for c in risk["controles"] if c["procedures"])["procedures"][0]
    p_url = f"{url}/procedures/{proc['id']}"

    resp = client.put(
        f"{p_url}/assignment",
        json={"assigne_a": str(aud.user.id), "echeance": "2026-02-15"},
        headers=chef.headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assigne_nom"] == aud.user.nom and body["echeance"] == "2026-02-15"
    assert body["statut"] == "a_faire" and body["en_retard"] is True

    mine = client.get("/api/me/procedures", headers=aud.headers).json()
    assert [(p["reference"], p["engagement_reference"]) for p in mine] == [
        (proc["reference"], m["reference"])
    ]
    assert mine[0]["controle"]

    # Avancement par la personne affectée.
    resp = client.put(f"{p_url}/status", json={"statut": "terminee"}, headers=aud.headers)
    assert resp.json()["statut"] == "terminee" and resp.json()["en_retard"] is False
    assert client.get("/api/me/procedures", headers=aud.headers).json() == []
    assert len(client.get("/api/me/procedures?a_faire=false", headers=aud.headers).json()) == 1

    # Contrôles : membre de l'équipe, échéance pendant la mission, droits.
    resp = client.put(
        f"{p_url}/assignment",
        json={"assigne_a": str(aud2.user.id), "echeance": None},
        headers=chef.headers,
    )
    assert resp.status_code == 422
    resp = client.put(
        f"{p_url}/assignment",
        json={"assigne_a": str(aud.user.id), "echeance": "2030-01-01"},
        headers=chef.headers,
    )
    assert resp.status_code == 422
    resp = client.put(
        f"{p_url}/assignment",
        json={"assigne_a": str(aud.user.id), "echeance": None},
        headers=aud.headers,
    )
    assert resp.status_code == 403
    others = [p for c in risk["controles"] for p in c["procedures"] if p["id"] != proc["id"]]
    resp = client.put(
        f"{url}/procedures/{others[0]['id']}/status",
        json={"statut": "en_cours"},
        headers=aud.headers,
    )
    assert resp.status_code == 403
    resp = client.put(
        f"{url}/procedures/{others[0]['id']}/status",
        json={"statut": "en_cours"},
        headers=chef.headers,
    )
    assert resp.json()["statut"] == "en_cours"
    # Désaffectation.
    resp = client.put(
        f"{p_url}/assignment", json={"assigne_a": None, "echeance": None}, headers=chef.headers
    )
    assert resp.json()["assigne_a"] is None
    matrix = client.get(f"{url}/matrix", headers=chef.headers).json()
    assert any(p["statut"] == "terminee" for c in matrix["controles"] for p in c["procedures"])
