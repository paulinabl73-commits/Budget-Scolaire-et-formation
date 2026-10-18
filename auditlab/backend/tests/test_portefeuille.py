"""RCO-01 : portefeuille de dossiers clients et clôtures par exercice (Module 6)."""

from app.security.roles import Role
from tests import helpers
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco01_portefeuille(client, account, cabinet, db):  # noqa: F811
    from app.models import AuditFile, Engagement

    expert, collab, directeur = cabinet["expert"], cabinet["collab"], cabinet["directeur"]
    c = new_client(client, cabinet, jour_cloture=30, mois_cloture=6)
    assert (
        c["expert_id"] == str(expert.user.id) and c["date_cloture"] == "30/06" and c["peut_gerer"]
    )
    assert c["collaborateur_nom"] == collab.user.nom and c["referentiel"].startswith("SYSCOHADA")
    # Le directeur désigne l'expert ; le collaborateur ne crée pas de dossier.
    body = {"raison_sociale": "Transports Kouamé", "forme_juridique": "SA", "regime_fiscal": "reel_normal",
            "framework_id": str(cabinet["framework"].id), "pays": "CI"}  # fmt: skip
    assert client.post("/api/clients", json=body, headers=directeur.headers).status_code == 422
    assert client.post("/api/clients", json=body, headers=collab.headers).status_code == 403
    bad = {**body, "expert_id": str(collab.user.id)}
    assert client.post("/api/clients", json=bad, headers=directeur.headers).status_code == 422
    other = new_client(
        client,
        cabinet,
        by="directeur",
        **{**body, "expert_id": str(expert.user.id), "collaborateur_id": None},
    )
    # Visibilité : un autre expert ne voit pas ce portefeuille, le collaborateur voit ses dossiers.
    stranger = account(Role.EXPERT_COMPTABLE)
    assert client.get("/api/clients", headers=stranger.headers).json() == []
    assert client.get(f"/api/clients/{c['id']}", headers=stranger.headers).status_code == 404
    assert [x["raison_sociale"] for x in client.get("/api/clients", headers=collab.headers).json()] == [
        "Boulangerie du Plateau SARL"]  # fmt: skip
    assert len(client.get("/api/clients", headers=directeur.headers).json()) == 2
    assert (
        client.patch(
            f"/api/clients/{c['id']}", json={"taille": "tpe"}, headers=collab.headers
        ).status_code
        == 403
    )
    assert client.patch(f"/api/clients/{other['id']}", json={"raison_sociale": "Transports Kouamé SA"},
                        headers=expert.headers).json()["raison_sociale"] == "Transports Kouamé SA"  # fmt: skip
    # Clôtures : exercice du 01/07 au 30/06, mission et dossier de révision, N-1 relié.
    first = open_closing(client, cabinet, c, 2025)
    second = open_closing(client, cabinet, c, 2026)
    assert client.post(f"/api/clients/{c['id']}/closings", json={"exercice": 2026},
                       headers=expert.headers).status_code == 409  # fmt: skip
    assert client.post(f"/api/clients/{c['id']}/closings", json={"exercice": 2027},
                       headers=collab.headers).status_code == 403  # fmt: skip
    file = db.get(AuditFile, second["audit_file_id"])
    assert (str(file.date_debut), str(file.date_fin), file.pays) == (
        "2025-07-01",
        "2026-06-30",
        "CI",
    )
    assert str(file.precedent_id) == first["audit_file_id"] and second["etape"] == "pieces"
    mission = db.get(Engagement, second["engagement_id"])
    assert mission.mode == "revision_comptable" and str(mission.date_fin) == "2026-12-30"
    roles = {str(m.user_id): m.role_mission for m in mission.members}
    assert roles == {str(expert.user.id): "chef_mission", str(collab.user.id): "auditeur"}
    # Le collaborateur travaille dans le dossier de révision ; la clôture n'est pas une mission d'audit.
    assert client.get(f"/api/audit-files/{file.id}", headers=collab.headers).json()[
        "peut_travailler"
    ]
    assert client.get("/api/engagements", headers=directeur.headers).json() == []
    assert (
        len(
            client.get("/api/engagements?mode=revision_comptable", headers=directeur.headers).json()
        )
        == 2
    )
    assert len(client.get("/api/clients", headers=expert.headers).json()[0]["clotures"]) == 2
    # Entités clientes hors univers d'audit ; experts et collaborateurs hors missions d'audit.
    assert client.get("/api/universe/entities", headers=directeur.headers).json() == []
    body = {"titre": "Audit", "date_debut": "2027-01-01", "date_fin": "2027-02-01", "budget_jours": 5,
            "membres": [{"user_id": str(collab.user.id), "role_mission": "auditeur"}]}  # fmt: skip
    assert client.post("/api/engagements", json=body, headers=directeur.headers).status_code == 422
    resp = client.post(
        "/api/universe/entities", json={"nom": "X", "type": "client"}, headers=directeur.headers
    )
    assert resp.status_code == 422
    assert helpers  # module importé pour les fixtures communes
