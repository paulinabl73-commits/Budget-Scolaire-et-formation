"""RCO-23 : revue du dossier par le superviseur puis l'expert-comptable (AUD-18 à AUD-20)."""

from app.richtext import from_plain_text
from app.security.roles import Role
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload

BALANCE = (
    "Compte;Intitulé;Solde débit;Solde crédit\n101000;Capital;;1000000\n521000;Banque;1000000;\n"
)


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
    # RCO-24 : états produits ; comptes de bilan revus par l'expert.
    resp = client.post(url, json={"niveau": "expert"}, headers=expert.headers)
    assert "États financiers non produits" in resp.json()["detail"]["message"]
    fid = closing["audit_file_id"]
    assert (
        upload(client, {"aud": collab}, fid, "b.csv", BALANCE.encode()).json()["statut"]
        == "accepte"
    )
    for compte in ("101000", "521000"):
        client.post(f"/api/audit-files/{fid}/justifications/{compte}/review", json={"commentaire": "Vu"},
                    headers=expert.headers)  # fmt: skip
    data = client.post(url, json={"niveau": "expert"}, headers=expert.headers).json()
    assert (
        set(data["revues"]) == {"superviseur", "expert"}
        and data["revues"]["expert"]["par"] == expert.user.nom
    )
    # Retrait du visa du superviseur : celui de l'expert tombe aussi.
    data = client.request("DELETE", f"{url}/superviseur", headers=sup.headers).json()
    assert data["revues"] == {}


def test_rco24_etats_cloture(client, cabinet):  # noqa: F811
    expert, collab = cabinet["expert"], cabinet["collab"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    assert (
        upload(client, {"aud": collab}, fid, "b.csv", BALANCE.encode()).json()["statut"]
        == "accepte"
    )
    entry = client.post(f"/api/audit-files/{fid}/provisions", json={
        "nature": "risque", "libelle": "Garantie", "montant_requis": "1000"}, headers=collab.headers)  # fmt: skip
    entry = client.post(f"/api/audit-files/{fid}/provisions/entry", headers=collab.headers).json()
    decided = client.post(f"/api/adjustments/{entry['id']}/decision", json={"statut": "acceptee"},
                          headers=expert.headers)  # fmt: skip
    assert decided.status_code == 200, decided.text
    states = client.get(f"/api/audit-files/{fid}/statements", headers=collab.headers)
    assert states.status_code == 200, states.text
    lines = [ln for s in states.json()["etats"].values() for ln in s if ln["ajustements"] != "0"]
    assert lines  # l'écriture d'inventaire acceptée figure dans les états révisés
