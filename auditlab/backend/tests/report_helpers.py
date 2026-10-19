"""Constats validés avec réponse et plan d'action (rapports et tableaux de bord, lot 10)."""

from tests.finding_helpers import create_finding


def validated_finding(client, team, criticite="elevee", titre=None):
    kw = {"criticite": criticite} | ({"titre": titre} if titre else {})
    f = create_finding(client, team, **kw)
    url = f"/api/findings/{f['id']}"
    client.post(f"{url}/send", json={"audite_id": str(team["audite"].user.id)},
                headers=team["aud"].headers)  # fmt: skip
    body = {"position": "accord_partiel", "commentaire": "8 créations sur 12 étaient urgentes",
            "plans": [{"description": "Réactiver le blocage", "echeance": "2027-06-30"}]}  # fmt: skip
    assert (
        client.post(f"{url}/response", json=body, headers=team["audite"].headers).status_code == 200
    )
    resp = client.post(f"{url}/validate", json={}, headers=team["chef"].headers)
    assert resp.status_code == 200, resp.text
    return resp.json()
