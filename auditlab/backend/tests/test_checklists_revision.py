"""RCO-07 : check-lists de révision par cycle, préremplies selon le référentiel et la taille."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco07_checklists(client, cabinet):  # noqa: F811
    collab = cabinet["collab"]
    tpe = new_client(client, cabinet, taille="tpe")
    big = new_client(client, cabinet, raison_sociale="Industries du Sud SA", taille="grande")
    small = client.get(
        f"/api/closings/{open_closing(client, cabinet, tpe)['id']}/checklist",
        headers=collab.headers,
    ).json()
    closing = open_closing(client, cabinet, big)
    url = f"/api/closings/{closing['id']}/checklist"
    data = client.get(url, headers=collab.headers).json()
    assert small["total"] < data["total"] == 45  # points CIPRES exclus d'un dossier SYSCOHADA
    assert data["cycles"][0]["cycle"] == "tresorerie" and data["avancement"] == 0
    assert (
        client.put(f"{url}/TRE-01", json={"statut": "anomalie"}, headers=collab.headers).status_code
        == 422
    )
    assert (
        client.put(f"{url}/OPS-01", json={"statut": "fait"}, headers=collab.headers).status_code
        == 404
    )
    client.put(f"{url}/TRE-01", json={"statut": "fait"}, headers=collab.headers)
    data = client.put(f"{url}/TRE-03", json={"statut": "anomalie", "commentaire": "Caisse créditrice en mars"},
                      headers=collab.headers).json()  # fmt: skip
    assert (data["traites"], data["anomalies"]) == (2, 1)
    point = next(p for p in data["cycles"][0]["points"] if p["code"] == "TRE-03")
    assert point["commentaire"] == "Caisse créditrice en mars"
    data = client.put(f"{url}/TRE-03", json={"statut": None}, headers=collab.headers).json()
    assert (data["traites"], data["anomalies"]) == (1, 0)
    assert (
        client.put(f"{url}/TRE-03", json={"statut": "fait"}, headers=collab.headers).json()[
            "traites"
        ]
        == 2
    )
