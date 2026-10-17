"""CON-07 : justificatifs déposés par l'audité, vérification ou rejet par l'audit."""

import datetime as dt
import io

from sqlalchemy import select

from app.models import AuditLog, Notification
from tests.finding_helpers import create_finding, team  # noqa: F401


def setup_plan(client, team):  # noqa: F811
    f = create_finding(client, team)
    body = {"description": "Réactiver le contrôle", "responsable_id": str(team["audite"].user.id),
            "echeance": str(dt.date.today() + dt.timedelta(days=30))}  # fmt: skip
    return f, client.post(
        f"/api/findings/{f['id']}/action-plans", json=body, headers=team["aud"].headers
    ).json()


def test_con07_depot_verification(client, team, db):  # noqa: F811
    f, plan = setup_plan(client, team)
    url = f"/api/action-plans/{plan['id']}"
    audite = team["audite"]
    resp = client.post(f"{url}/evidence", files={"file": ("capture.png", io.BytesIO(b"\x89PNG\r\n\x1a\nxx"))},
                       data={"commentaire": "Écran de paramétrage"}, headers=audite.headers)  # fmt: skip
    assert resp.status_code == 201, resp.text
    ev = resp.json()
    assert ev["nom_fichier"] == "capture.png" and len(ev["sha256"]) == 64
    assert (
        db.scalar(select(Notification).where(Notification.type == "plan_justificatif")) is not None
    )
    listed = client.get(f"{url}/evidence", headers=team["aud"].headers).json()
    assert [e["commentaire"] for e in listed] == ["Écran de paramétrage"]
    # Téléchargement par lien signé, puis par session (journalisé).
    content = client.get(listed[0]["url"])
    assert content.status_code == 200 and content.content.startswith(b"\x89PNG")
    content = client.get(f"/api/plan-evidence/{ev['id']}/content", headers=team["chef"].headers)
    assert content.headers["x-content-sha256"] == ev["sha256"]
    assert db.scalar(
        select(AuditLog).where(
            AuditLog.action == "download", AuditLog.object_type == "PlanEvidence"
        )
    )
    # Rejet motivé, puis nouvelle déclaration et vérification.
    client.post(f"{url}/status", json={"statut": "realise"}, headers=audite.headers)
    assert (
        client.post(
            f"{url}/reject", json={"commentaire": ""}, headers=team["aud"].headers
        ).status_code
        == 422
    )
    assert (
        client.post(f"{url}/reject", json={"commentaire": "x"}, headers=audite.headers).status_code
        == 403
    )
    resp = client.post(
        f"{url}/reject", json={"commentaire": "Capture illisible"}, headers=team["aud"].headers
    )
    assert resp.json()["statut"] == "en_cours" and "Capture illisible" in resp.json()["commentaire"]
    assert (
        client.post(
            f"{url}/reject", json={"commentaire": "x"}, headers=team["aud"].headers
        ).status_code
        == 409
    )
    client.post(f"{url}/status", json={"statut": "realise"}, headers=audite.headers)
    resp = client.post(f"{url}/status", json={"statut": "verifie"}, headers=team["aud"].headers)
    assert resp.json()["statut"] == "verifie"
    kinds = set(db.scalars(select(Notification.type).where(Notification.user_id == audite.user.id)))
    assert {"plan_rejete", "plan_verifie"} <= kinds
    # Plan clos : plus de dépôt.
    resp = client.post(
        f"{url}/evidence", files={"file": ("a.txt", io.BytesIO(b"x"))}, headers=audite.headers
    )
    assert resp.status_code == 409


def test_con07_controles(client, team, account):  # noqa: F811
    from app.security.roles import Role

    _, plan = setup_plan(client, team)
    url = f"/api/action-plans/{plan['id']}/evidence"
    bad = client.post(
        url, files={"file": ("x.exe", io.BytesIO(b"MZ"))}, headers=team["audite"].headers
    )
    assert bad.status_code == 415
    fake = client.post(
        url, files={"file": ("x.pdf", io.BytesIO(b"pas un pdf"))}, headers=team["audite"].headers
    )
    assert fake.status_code == 415
    other = account(Role.AUDITE)
    assert (
        client.post(
            url, files={"file": ("a.txt", io.BytesIO(b"x"))}, headers=other.headers
        ).status_code
        == 404
    )
    assert (
        client.post(
            url, files={"file": ("a.txt", io.BytesIO(b"x"))}, headers=team["da"].headers
        ).status_code
        == 403
    )
    assert client.get("/api/plan-evidence/00000000-0000-0000-0000-000000000000/content",
                      headers=team["aud"].headers).status_code == 404  # fmt: skip
