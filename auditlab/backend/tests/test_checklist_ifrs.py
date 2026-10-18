"""IFR-04 : check-list des informations à fournir en annexe, par norme, cochée par l'auditeur."""

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load
from tests.test_ifrs import IAS19


def test_ifr04_checklist(client, rev):  # noqa: F811
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    aud = rev["aud"].headers
    data = client.get(f"{base}/ifrs/checklist", headers=aud).json()
    normes = {n["norme"]: n for n in data["normes"]}
    assert data["total"] == 48 and data["repondus"] == 0
    assert normes["IAS 1"]["applicable"] and not normes["IAS 19"]["applicable"]
    # Une norme devient applicable dès qu'un retraitement validé la mobilise.
    load(client, rev, f["id"])
    adj = client.post(f"{base}/adjustments", json=IAS19, headers=aud).json()
    client.post(f"/api/adjustments/{adj['id']}/decision", json={"statut": "acceptee"}, headers=aud)
    assert {
        n["norme"]: n for n in client.get(f"{base}/ifrs/checklist", headers=aud).json()["normes"]
    }["IAS 19"]["applicable"]
    url = f"{base}/ifrs/checklist"
    assert client.put(f"{url}/IAS 19-03", json={"reponse": "non"}, headers=aud).status_code == 422
    assert client.put(f"{url}/IAS 99-01", json={"reponse": "oui"}, headers=aud).status_code == 404
    assert (
        client.put(
            f"{url}/IAS 1-01", json={"reponse": "oui"}, headers=rev["da"].headers
        ).status_code
        == 403
    )
    client.put(f"{url}/IAS 1-01", json={"reponse": "oui"}, headers=aud)
    data = client.put(
        f"{url}/IAS 19-03",
        json={"reponse": "non", "commentaire": "Taux d'actualisation non indiqué"},
        headers=aud,
    ).json()
    assert (data["repondus"], data["informations_manquantes"]) == (2, 1)
    point = next(
        p
        for n in data["normes"]
        if n["norme"] == "IAS 19"
        for p in n["points"]
        if p["code"] == "IAS 19-03"
    )
    assert point["libelle"] == "Principales hypothèses actuarielles" and point[
        "commentaire"
    ].startswith("Taux")
    data = client.put(f"{url}/IAS 19-03", json={"reponse": "oui"}, headers=aud).json()
    assert data["informations_manquantes"] == 0 and data["repondus"] == 2
