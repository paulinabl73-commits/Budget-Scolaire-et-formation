"""CIP-08 : mission d'inspection CIPRES (rapports provisoire et définitif, suivi des
recommandations d'une inspection à l'autre)."""

import datetime as dt

from app.security.roles import Role
from tests import helpers
from tests.finding_helpers import FINDING


def contradictory(client, insp, audite, mission_id, validate=True, **kw):
    f = client.post(
        f"/api/engagements/{mission_id}/findings", json={**FINDING, **kw}, headers=insp.headers
    ).json()
    resp = client.post(
        f"/api/findings/{f['id']}/send",
        json={"audite_id": str(audite.user.id)},
        headers=insp.headers,
    )
    assert resp.status_code == 200, resp.text
    if validate:
        respond_and_validate(client, insp, audite, f)
    return f


def respond_and_validate(client, insp, audite, f):
    body = {"position": "accord", "commentaire": "Le contrôle sera réactivé en mars."}
    assert (
        client.post(
            f"/api/findings/{f['id']}/response", json=body, headers=audite.headers
        ).status_code
        == 200
    )
    resp = client.post(f"/api/findings/{f['id']}/validate", json={"commentaire": "Réponse satisfaisante."},
                       headers=insp.headers)  # fmt: skip
    assert resp.status_code == 200, resp.text


def test_cip08_inspection(client, account):
    directeur, insp, aud, audite = (
        account(r) for r in (Role.DIRECTEUR, Role.INSPECTEUR_CIPRES, Role.AUDITEUR, Role.AUDITE)
    )
    ops = helpers.entity(client, directeur.headers, "Caisse nationale de prévoyance sociale")
    team = [(insp.user, "chef_mission"), (aud.user, "auditeur")]
    # L'inspecteur n'intervient que sur les missions d'inspection.
    body = {"titre": "Audit", "date_debut": "2025-03-01", "date_fin": "2025-04-30", "budget_jours": 20,
            "membres": [{"user_id": str(insp.user.id), "role_mission": "chef_mission"}]}  # fmt: skip
    assert client.post("/api/engagements", json=body, headers=directeur.headers).status_code == 422
    first = helpers.mission(client, directeur.headers, team, titre="Inspection 2025", entity_id=ops["id"],
                            mode="inspection_cipres", date_debut="2025-03-01", date_fin="2025-04-30")  # fmt: skip
    assert first["mode"] == "inspection_cipres"
    old = contradictory(
        client, insp, audite, first["id"], titre="Pensions servies sans certificat de vie"
    )
    second = helpers.mission(client, directeur.headers, team, titre="Inspection 2026", entity_id=ops["id"],
                             mode="inspection_cipres", date_debut="2026-03-01", date_fin="2026-04-30")  # fmt: skip
    url = f"/api/engagements/{second['id']}/inspection"
    data = client.get(url, headers=insp.headers).json()
    [previous] = data["recommandations_anterieures"]
    assert (previous["reference"], previous["mission"], previous["suivi"]) == (
        old["reference"],
        first["reference"],
        None,
    )
    assert data["blocages"]["provisoire"] == ["Aucun constat"]
    # Rapport provisoire : constats soumis à l'organisme, date limite postérieure à ce jour.
    current = client.post(
        f"/api/engagements/{second['id']}/findings", json=FINDING, headers=insp.headers
    ).json()
    limit = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    resp = client.post(
        f"{url}/provisional", json={"date_limite_reponse": limit}, headers=insp.headers
    )
    assert resp.status_code == 409 and resp.json()["detail"]["points"][0].startswith(
        "Constats non soumis"
    )
    client.post(
        f"/api/findings/{current['id']}/send",
        json={"audite_id": str(audite.user.id)},
        headers=insp.headers,
    )
    assert (
        client.post(
            f"{url}/provisional", json={"date_limite_reponse": limit}, headers=aud.headers
        ).status_code
        == 403
    )
    past = {"date_limite_reponse": dt.date.today().isoformat()}
    assert client.post(f"{url}/provisional", json=past, headers=insp.headers).status_code == 422
    provisional = client.post(
        f"{url}/provisional", json={"date_limite_reponse": limit}, headers=insp.headers
    ).json()
    assert len(provisional["sha256"]) == 64 and provisional["date_limite_reponse"] == limit
    assert (
        client.post(
            f"{url}/provisional", json={"date_limite_reponse": limit}, headers=insp.headers
        ).status_code
        == 409
    )
    # Réponse générale de l'organisme, puis rapport définitif.
    answer = {
        "reponse": "L'organisme prend acte des constats.",
        "recue_le": dt.date.today().isoformat(),
    }
    assert (
        client.put(f"{url}/response", json=answer, headers=insp.headers).json()["reponse_organisme"]
        == answer["reponse"]
    )
    resp = client.post(f"{url}/final", json={}, headers=insp.headers)
    assert resp.status_code == 409
    assert {p.split(" : ")[0] for p in resp.json()["detail"]["points"]} == {
        "Constats non validés", "Suivi non renseigné des recommandations"}  # fmt: skip
    respond_and_validate(client, insp, audite, current)
    follow = {
        "statut": "partielle",
        "commentaire": "Certificats de vie collectés pour 80 % des pensionnés.",
    }
    assert (
        client.put(f"{url}/follow-ups/{old['id']}", json=follow, headers=aud.headers).status_code
        == 403
    )
    assert (
        client.put(
            f"{url}/follow-ups/{current['id']}", json=follow, headers=insp.headers
        ).status_code
        == 404
    )
    data = client.put(f"{url}/follow-ups/{old['id']}", json=follow, headers=insp.headers).json()
    assert data["recommandations_anterieures"][0]["suivi"]["statut"] == "partielle"
    assert data["blocages"]["definitif"] == []
    final = client.post(f"{url}/final", json={}, headers=insp.headers).json()
    assert final["destinataire"] == "Commission de surveillance de la CIPRES"
    assert (
        client.put(f"{url}/follow-ups/{old['id']}", json=follow, headers=insp.headers).status_code
        == 409
    )
    assert client.put(f"{url}/response", json=answer, headers=insp.headers).status_code == 409
    # Contenu figé et exports.

    reports = {r["version"]: r for r in client.get(url, headers=insp.headers).json()["rapports"]}
    assert set(reports) == {"provisoire", "definitif"}
    pdf = client.get(f"/api/inspection-reports/{final['id']}/export", headers=aud.headers)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = client.get(
        f"/api/inspection-reports/{final['id']}/export?format=docx", headers=insp.headers
    )
    assert docx.status_code == 200 and docx.content[:2] == b"PK"


def test_cip08_contenu_des_rapports(client, account, db):
    from app.models import InspectionReport

    directeur, insp, audite = (
        account(r) for r in (Role.DIRECTEUR, Role.INSPECTEUR_CIPRES, Role.AUDITE)
    )
    ops = helpers.entity(client, directeur.headers, "Caisse de retraite")
    m = helpers.mission(client, directeur.headers, [(insp.user, "chef_mission")], titre="Inspection", entity_id=ops["id"],
                        mode="inspection_cipres", objectifs="Contrôle de la branche pensions")  # fmt: skip
    url = f"/api/engagements/{m['id']}/inspection"
    f = contradictory(client, insp, audite, m["id"], validate=False, criticite="critique")
    limit = (dt.date.today() + dt.timedelta(days=15)).isoformat()
    provisional = db.get(InspectionReport, client.post(f"{url}/provisional", json={"date_limite_reponse": limit},
                                                      headers=insp.headers).json()["id"])  # fmt: skip
    text = "\n".join(str(b) for b in provisional.blocs)
    assert (
        "Première inspection" in text
        and "critique 1" in text
        and "Réponse de l'organisme" not in text
    )
    assert (
        f"{dt.date.fromisoformat(limit):%d/%m/%Y}" in text
        and "Contrôle de la branche pensions" in text
    )
    respond_and_validate(client, insp, audite, f)
    final = db.get(InspectionReport, client.post(f"{url}/final", json={"destinataire": "Commission de surveillance"},
                                                 headers=insp.headers).json()["id"])  # fmt: skip
    text = "\n".join(str(b) for b in final.blocs)
    assert (
        "Destinataire : Commission de surveillance." in text
        and "Réponse de l'organisme : Accord" in text
    )
    assert (
        "Position de l'inspection : Réponse satisfaisante." in text
        and "Aucune réponse générale reçue." in text
    )
    # Mission d'audit ordinaire : pas de volet inspection.
    audit = helpers.mission(client, directeur.headers, titre="Audit des achats")
    assert (
        client.get(
            f"/api/engagements/{audit['id']}/inspection", headers=directeur.headers
        ).status_code
        == 409
    )
