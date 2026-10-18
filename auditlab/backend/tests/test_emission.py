"""REV-28 : signature de l'associé ou du chef de mission, émission, verrouillage et archive."""

import hashlib

from app.security.roles import Role
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load
from tests.test_ajustements import PROVISION


def test_rev28_signature_et_emission(client, rev, account, db):  # noqa: F811
    from app.models import EngagementMember

    aud, chef = rev["aud"].headers, rev["chef"].headers
    associe = account(Role.ASSOCIE)
    db.add(
        EngagementMember(
            engagement_id=rev["mission"]["id"], user_id=associe.user.id, role_mission="superviseur"
        )
    )
    db.commit()
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    load(client, rev, f["id"])
    client.put(
        f"{base}/materiality",
        headers=chef,
        json={
            "base_seuil": "total_bilan",
            "pct_seuil": "1.5",
            "justification": "Total du bilan retenu",
        },
    )
    adj = client.post(f"{base}/adjustments", json=PROVISION, headers=aud).json()
    assert (
        client.post(f"{base}/opinion/sign", headers=associe.headers).status_code == 409
    )  # opinion à rédiger
    client.put(
        f"{base}/opinion", json={"type_opinion": "sans_reserve", "lieu": "Abidjan"}, headers=chef
    )
    # Points bloquants : conclusion non rédigée, écriture en attente de décision.
    resp = client.post(f"{base}/opinion/sign", headers=associe.headers)
    assert resp.status_code == 409
    assert resp.json()["detail"]["points"] == [
        "Conclusion de la note de synthèse non rédigée",
        "Écritures d'ajustement en attente de la décision de l'entité",
    ]
    client.post(f"/api/adjustments/{adj['id']}/decision", json={"statut": "acceptee"}, headers=aud)
    client.put(
        f"{base}/synthesis/conclusion",
        json={"conclusion": "Travaux achevés, comptes réguliers et sincères."},
        headers=chef,
    )
    # Signature : l'associé ou le chef de mission, jamais l'auditeur.
    assert client.post(f"{base}/opinion/sign", headers=aud).status_code == 403
    signed = client.post(f"{base}/opinion/sign", headers=associe.headers).json()
    assert signed["statut"] == "signe" and signed["signe_par"] and len(signed["empreinte"]) == 64
    assert (
        client.put(
            f"{base}/opinion", json={"type_opinion": "sans_reserve"}, headers=chef
        ).status_code
        == 409
    )
    assert client.post(f"{base}/opinion/sign", headers=chef).status_code == 409  # déjà signée
    # Un changement des états après signature invalide l'émission ; nouvelle signature.
    client.put(f"{base}/opinion", json={}, headers=chef)
    client.post(f"{base}/opinion/unsign", headers=associe.headers)
    client.put(
        f"{base}/opinion", json={"type_opinion": "sans_reserve", "lieu": "Dakar"}, headers=chef
    )
    client.post(f"{base}/opinion/sign", headers=chef)
    second = client.post(f"{base}/adjustments", json=PROVISION, headers=aud).json()
    client.post(
        f"/api/adjustments/{second['id']}/decision", json={"statut": "acceptee"}, headers=aud
    )
    resp = client.post(f"{base}/opinion/emit", headers=chef)
    assert resp.status_code == 409 and "signez à nouveau" in resp.text
    client.post(f"{base}/opinion/unsign", headers=chef)
    client.post(f"{base}/opinion/sign", headers=associe.headers)
    emitted = client.post(f"{base}/opinion/emit", headers=associe.headers).json()
    assert emitted["statut"] == "emis" and emitted["emis_par"] and emitted["archive_sha256"]
    # Dossier verrouillé : plus aucune écriture ; archive intègre et téléchargeable.
    assert client.get(base, headers=aud).json()["statut"] == "archive"
    assert client.post(f"{base}/adjustments", json=PROVISION, headers=aud).status_code == 409
    assert client.put(f"{base}/materiality", headers=chef, json={"base_seuil": "total_bilan", "pct_seuil": "1",
                      "justification": "Total du bilan retenu"}).status_code == 409  # fmt: skip
    assert client.post(f"{base}/opinion/unsign", headers=chef).status_code == 409
    pdf = client.get(f"{base}/opinion/archive", headers=aud)
    assert (
        pdf.content.startswith(b"%PDF")
        and hashlib.sha256(pdf.content).hexdigest() == emitted["archive_sha256"]
    )
    report = client.get(f"{base}/reports/opinion?format=pdf", headers=aud)
    assert report.status_code == 200
