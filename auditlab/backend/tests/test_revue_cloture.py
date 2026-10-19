"""RCO-23 : revue du dossier par le superviseur puis l'expert-comptable (AUD-18 à AUD-20)."""

from app.richtext import from_plain_text
from app.security.roles import Role
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco23_revue(client, cabinet, account):  # noqa: F811
    expert, collab = cabinet["expert"], cabinet["collab"]
    sup = account(Role.CHEF_MISSION)
    c = new_client(client, cabinet, superviseur_id=str(sup.user.id))
    closing = open_closing(client, cabinet, c)
    url = f"/api/closings/{closing['id']}/review"
    wp = client.post(f"/api/engagements/{closing['engagement_id']}/workpapers", headers=collab.headers, json={
        "reference": "TRE-1", "titre": "Trésorerie", "travaux": from_plain_text("Rapprochements"),
        "conclusion": "Satisfaisant", "evaluation": "efficace"}).json()  # fmt: skip

    def sign(acc, kind):
        resp = client.post(
            f"/api/workpapers/{wp['id']}/signoffs", json={"type": kind}, headers=acc.headers
        )
        assert resp.status_code in (200, 201), resp.text

    sign(collab, "prepare")
    data = client.get(url, headers=collab.headers).json()
    assert data["blocages"]["superviseur"] == ["Papiers de travail non revus : TRE-1"]
    assert "Visa du superviseur attendu" in data["blocages"]["expert"]
    assert (
        client.post(url, json={"niveau": "superviseur"}, headers=collab.headers).status_code == 403
    )
    assert client.post(url, json={"niveau": "superviseur"}, headers=sup.headers).status_code == 409
    sign(sup, "revu")
    assert (
        "superviseur"
        in client.post(url, json={"niveau": "superviseur"}, headers=sup.headers).json()["revues"]
    )
    # Note de revue de l'expert : bloque son visa jusqu'à la clôture de la note.
    note = client.post(f"/api/workpapers/{wp['id']}/review-notes", headers=expert.headers,
                       json={"texte": "Joindre le relevé", "ancre": {"champ": "travaux", "citation": "Rapprochements"}}).json()  # fmt: skip
    resp = client.post(url, json={"niveau": "expert"}, headers=expert.headers)
    assert (
        resp.status_code == 409
        and "1 note(s) de revue ouverte(s)" in resp.json()["detail"]["points"]
    )
    client.post(f"/api/review-notes/{note['id']}/close", headers=expert.headers)
    sign(expert, "approuve")
    data = client.post(url, json={"niveau": "expert"}, headers=expert.headers).json()
    assert (
        set(data["revues"]) == {"superviseur", "expert"}
        and data["revues"]["expert"]["par"] == expert.user.nom
    )
    # Retrait du visa du superviseur : celui de l'expert tombe aussi.
    data = client.request("DELETE", f"{url}/superviseur", headers=sup.headers).json()
    assert data["revues"] == {}
