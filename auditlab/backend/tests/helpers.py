"""Constructeurs de données de test partagés entre les lots."""

from fastapi.testclient import TestClient


def entity(client: TestClient, headers: dict, nom: str = "Achats", **kw) -> dict:
    resp = client.post(
        "/api/universe/entities", json={"nom": nom, "type": "processus", **kw}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def validated_plan(client: TestClient, headers: dict, entities: list[dict], annee: int = 2027):
    plan = client.post("/api/plans", json={"annee": annee}, headers=headers).json()
    items = []
    for i, e in enumerate(entities):
        resp = client.post(
            f"/api/plans/{plan['id']}/items",
            json={
                "entity_id": e["id"],
                "budget_jours": 20 + i,
                "periode_debut": f"{annee}-0{i + 1}-01",
                "periode_fin": f"{annee}-0{i + 1}-28",
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        items.append(resp.json())
    resp = client.post(f"/api/plans/{plan['id']}/validate", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json(), items


def mission(client: TestClient, headers: dict, membres: list[tuple] = (), **kw) -> dict:
    body = {
        "titre": "Audit des achats",
        "date_debut": "2027-02-01",
        "date_fin": "2027-03-31",
        "budget_jours": 30,
        **kw,
        "membres": [{"user_id": str(u.id), "role_mission": r} for u, r in membres],
    }
    resp = client.post("/api/engagements", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()
