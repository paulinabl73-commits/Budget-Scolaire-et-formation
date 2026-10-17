"""REV-16 : programmes de travail types par cycle, adaptables par référentiel."""

from app.security.roles import Role
from tests.revision_helpers import create_file, rev  # noqa: F401


def test_rev16_bibliotheque_et_application(client, rev, account):  # noqa: F811
    chef, aud = rev["chef"].headers, rev["aud"].headers
    admin = account(Role.ADMIN).headers
    lib = client.get("/api/revision-programs", headers=aud).json()
    assert lib["referentiel"] == "SYSCOHADA" and len(lib["cycles"]) == 11
    assert len(lib["procedures"]) == 50 and len(lib["assertions"]) == 6
    tresorerie = [p for p in lib["procedures"] if p["cycle"] == "tresorerie"]
    assert len(tresorerie) == 5 and tresorerie[0]["description"].startswith(
        "Obtenir les confirmations bancaires"
    )
    # Un référentiel sans programme propre utilise celui de SYSCOHADA, puis reçoit le sien.
    assert (
        client.get("/api/revision-programs?referentiel=CIPRES", headers=aud).json()["referentiel"]
        == "SYSCOHADA"
    )
    step = {"referentiel": "CIPRES", "cycle": "clients", "assertion": "exhaustivite",
            "description": "Rapprocher les cotisations émises des déclarations nominatives des employeurs."}  # fmt: skip
    assert client.post("/api/revision-programs", json=step, headers=chef).status_code == 403
    assert (
        client.post(
            "/api/revision-programs", json={**step, "cycle": "inconnu"}, headers=admin
        ).status_code
        == 422
    )
    created = client.post("/api/revision-programs", json=step, headers=admin).json()
    cipres = client.get("/api/revision-programs?referentiel=CIPRES", headers=aud).json()
    assert cipres["referentiel"] == "CIPRES" and [p["id"] for p in cipres["procedures"]] == [
        created["id"]
    ]
    # Adaptation : une procédure désactivée n'est plus reprise.
    caisse = next(p for p in tresorerie if "caisse" in p["description"])
    resp = client.patch(
        f"/api/revision-programs/{caisse['id']}", json={"actif": False}, headers=admin
    )
    assert resp.status_code == 200 and resp.json()["actif"] is False
    assert client.patch("/api/revision-programs/00000000-0000-0000-0000-000000000000", json={},
                        headers=admin).status_code == 404  # fmt: skip
    # Application au programme de la mission (chef de mission), sans doublon.
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}/programs"
    assert client.post(f"{url}/tresorerie/apply", headers=aud).status_code == 403
    assert client.post(f"{url}/inconnu/apply", headers=chef).status_code == 404
    first = client.post(f"{url}/tresorerie/apply", headers=chef).json()
    assert (first["procedures_ajoutees"], first["procedures_programme"]) == (4, 4)
    assert client.post(f"{url}/tresorerie/apply", headers=chef).json()["procedures_ajoutees"] == 0
    matrix = client.get(f"{rev['url']}/matrix", headers=chef).json()
    risk = next(
        r for r in matrix["risques"] if r["libelle"] == "Trésorerie – programme de révision type"
    )
    descriptions = [p["description"] for c in risk["controles"] for p in c["procedures"]]
    assert len(descriptions) == 4 and descriptions[0].startswith(
        "[Existence] Obtenir les confirmations"
    )
    assert risk["cycle"] == "tresorerie"
