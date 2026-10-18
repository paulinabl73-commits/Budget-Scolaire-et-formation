"""REV-27 : modèles de rapports paramétrables (opinion, conventions, lettre d'affirmation)."""

import io

from docx import Document

from app.security.roles import Role
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load
from tests.test_ajustements import PROVISION


def text_of(resp) -> str:
    return "\n".join(p.text for p in Document(io.BytesIO(resp.content)).paragraphs)


def test_rev27_modeles_et_rapports(client, rev, account):  # noqa: F811
    aud, chef, admin = rev["aud"].headers, rev["chef"].headers, account(Role.ADMIN).headers
    templates = client.get("/api/report-templates", headers=aud).json()
    assert [t["code"] for t in templates] == ["affirmation", "conventions", "opinion"]
    # Modèle modifiable par l'administrateur seulement, versionné.
    sections = next(t for t in templates if t["code"] == "affirmation")["sections"]
    assert (
        client.put(
            "/api/report-templates/affirmation", json={"sections": sections}, headers=chef
        ).status_code
        == 403
    )
    bad = [{"titre": "X", "texte": "y", "si": "inconnu"}]
    assert (
        client.put(
            "/api/report-templates/affirmation", json={"sections": bad}, headers=admin
        ).status_code
        == 422
    )
    edited = [
        *sections[:-1],
        {"titre": "Engagements", "texte": "Aucun engagement hors bilan non communiqué."},
        sections[-1],
    ]
    assert (
        client.put(
            "/api/report-templates/affirmation", json={"sections": edited}, headers=admin
        ).json()["version"]
        == 2
    )
    # Opinion du dossier : suggestion fondée sur les anomalies non corrigées (REV-22).
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
    client.post(f"{base}/adjustments", json=PROVISION, headers=aud)  # proposée, non corrigée
    opinion = client.get(f"{base}/opinion", headers=aud).json()
    assert opinion["statut"] == "a_rediger" and opinion["suggestion"] == "avec_reserve"
    assert client.get(f"{base}/reports/opinion", headers=aud).status_code == 409
    body = {"type_opinion": "avec_reserve", "lieu": "Abidjan"}
    assert (
        client.put(f"{base}/opinion", json=body, headers=chef).status_code == 422
    )  # fondement manquant
    body["fondement"] = (
        "La créance Alpha (500 000 FCFA) n'est pas dépréciée alors que le client est en redressement judiciaire."
    )
    assert client.put(f"{base}/opinion", json=body, headers=aud).status_code == 403
    saved = client.put(f"{base}/opinion", json=body, headers=chef).json()
    assert saved["statut"] == "brouillon" and saved["type_opinion"] == "avec_reserve"
    text = text_of(client.get(f"{base}/reports/opinion?format=docx", headers=aud))
    assert text.startswith("PROJET – Rapport du commissaire aux comptes")
    assert "Opinion avec réserve" in text and "Fondement de l'opinion avec réserve" in text
    assert "redressement judiciaire" in text and "Opinion défavorable" not in text
    assert "SYSCOHADA révisé" in text and "Abidjan, le" in text
    # Rapport spécial : sans convention, puis avec une convention déclarée.
    assert "aucune convention réglementée" in text_of(
        client.get(f"{base}/reports/conventions?format=docx", headers=aud)
    )
    body["conventions"] = [
        {
            "objet": "Bail du siège consenti par l'administrateur M. Koné",
            "parties": "M. Koné, administrateur",
            "montant": "12 000 000 FCFA par an",
        }
    ]
    client.put(f"{base}/opinion", json=body, headers=chef)
    assert "Bail du siège" in text_of(
        client.get(f"{base}/reports/conventions?format=docx", headers=aud)
    )
    affirmation = client.get(f"{base}/reports/affirmation?format=docx", headers=aud)
    assert "Aucun engagement hors bilan" in text_of(affirmation)
    pdf = client.get(f"{base}/reports/opinion?format=pdf", headers=aud)
    assert pdf.content.startswith(b"%PDF")
    assert client.get(f"{base}/reports/inconnu", headers=aud).status_code == 404
