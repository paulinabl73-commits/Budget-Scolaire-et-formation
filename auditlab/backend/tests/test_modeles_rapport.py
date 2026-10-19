"""REP-01 : modèles de rapport paramétrables (logo, page de garde, sections, ordre)."""

import io

import pytest

from app.reporting import templates
from app.security.roles import Role

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def modele(db):
    t = templates.seed(db)
    db.commit()
    return t


def test_rep01_modeles(client, account, modele):
    directeur, chef = account(Role.DIRECTEUR).headers, account(Role.CHEF_MISSION).headers
    listed = client.get("/api/mission-report-templates", headers=chef).json()
    assert listed[0]["par_defaut"] and [s["code"] for s in listed[0]["sections"]] == [
        "synthese", "contexte", "constats", "plans_action", "annexes"]  # fmt: skip
    body = {**{k: listed[0][k] for k in ("page_garde", "pied_de_page", "actif")},
            "nom": "Rapport court", "ordre_constats": "reference",
            "sections": list(reversed(listed[0]["sections"]))}  # fmt: skip
    assert client.post("/api/mission-report-templates", json=body, headers=chef).status_code == 403
    bad = {**body, "sections": body["sections"][:-1]}
    assert (
        client.post("/api/mission-report-templates", json=bad, headers=directeur).status_code == 422
    )
    no_findings = {
        **body,
        "sections": [{**s, "actif": s["code"] != "constats"} for s in body["sections"]],
    }
    assert (
        client.post(
            "/api/mission-report-templates", json=no_findings, headers=directeur
        ).status_code
        == 422
    )
    t = client.post("/api/mission-report-templates", json=body, headers=directeur).json()
    assert not t["par_defaut"] and t["sections"][0]["code"] == "annexes"
    url = f"/api/mission-report-templates/{t['id']}"
    assert client.put(f"{url}/logo", files={"file": ("x.gif", io.BytesIO(b"GIF89a"))},
                      headers=directeur).status_code == 415  # fmt: skip
    assert client.put(
        f"{url}/logo", files={"file": ("logo.png", io.BytesIO(PNG))}, headers=directeur
    ).json()["logo"]
    assert client.get(f"{url}/logo", headers=chef).content == PNG
    assert client.post(f"{url}/default", headers=directeur).json()["par_defaut"]
    assert client.delete(url, headers=directeur).status_code == 409  # modèle par défaut
    old = f"/api/mission-report-templates/{modele.id}"
    assert client.delete(old, headers=directeur).status_code == 204
    assert [x["nom"] for x in client.get("/api/mission-report-templates", headers=chef).json()] == [
        "Rapport court"
    ]
