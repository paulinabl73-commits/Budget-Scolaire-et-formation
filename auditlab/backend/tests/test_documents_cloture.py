"""RCO-25 : documents de la clôture (modèles paramétrables, attestation signée par l'expert)."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_revue_cloture import BALANCE


def test_rco25_documents(client, cabinet):  # noqa: F811
    expert, collab = cabinet["expert"], cabinet["collab"]
    closing = open_closing(client, cabinet, new_client(client, cabinet))
    url, fid = f"/api/closings/{closing['id']}/documents", closing["audit_file_id"]
    data = client.get(url, headers=collab.headers).json()
    assert [m["code"] for m in data["modeles"]] == [
        "presentation", "lettre_mission_cloture", "recommandations", "note_cloture"
    ]  # fmt: skip
    assert data["signature"] is None and not data["peut_signer"]
    params = {"lieu": "Abidjan", "honoraires": "1 500 000 XOF HT", "observations": "",
              "recommandations": [{"constat": "Caisse non arrêtée mensuellement",
                                   "recommandation": "Établir un brouillard de caisse"}]}  # fmt: skip
    assert client.put(url, json=params, headers=collab.headers).status_code == 200
    for code in ("lettre_mission_cloture", "recommandations", "note_cloture"):
        resp = client.get(f"{url}/{code}?format=docx", headers=collab.headers)
        assert resp.status_code == 200 and resp.content[:2] == b"PK"
    import io

    from docx import Document

    text = "\n".join(p.text for p in Document(io.BytesIO(
        client.get(f"{url}/recommandations?format=docx", headers=collab.headers).content)).paragraphs)  # fmt: skip
    assert "1. Caisse non arrêtée mensuellement — Recommandation : Établir" in text
    pdf = client.get(f"{url}/presentation", headers=collab.headers)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert client.get(f"{url}/opinion", headers=collab.headers).status_code == 404

    sign = f"{url}/presentation/sign"
    assert client.post(sign, headers=collab.headers).status_code == 403
    assert client.post(sign, headers=expert.headers).json()["detail"].startswith("Visa de revue")
    assert (
        upload(client, {"aud": collab}, fid, "b.csv", BALANCE.encode()).json()["statut"]
        == "accepte"
    )
    for compte in ("101000", "521000"):
        client.post(f"/api/audit-files/{fid}/justifications/{compte}/review",
                    json={"commentaire": "Vu"}, headers=expert.headers)  # fmt: skip
    review = f"/api/closings/{closing['id']}/review"
    assert client.post(review, json={"niveau": "expert"}, headers=expert.headers).status_code == 200
    signed = client.post(sign, headers=expert.headers).json()["signature"]
    assert signed["par"] and signed["conforme"] and len(signed["empreinte"]) == 64
    assert client.post(sign, headers=expert.headers).status_code == 409
    params["observations"] = "Changement de méthode"
    assert client.put(url, json=params, headers=collab.headers).status_code == 409
    assert client.delete(f"{review}/expert", headers=expert.headers).status_code == 409
    # Une modification du dossier après signature est signalée.
    client.put(url, json={**params, "observations": ""}, headers=collab.headers)
    assert upload(client, {"aud": collab}, fid, "b2.csv", BALANCE.replace("1000000", "2000000").encode()).json()["statut"] == "accepte"  # fmt: skip
    assert client.get(url, headers=collab.headers).json()["signature"]["conforme"] is False
    assert client.delete(sign, headers=expert.headers).json()["signature"] is None
