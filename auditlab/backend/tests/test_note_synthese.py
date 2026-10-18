"""REV-26 : note de synthèse générée."""

import io

from docx import Document

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load
from tests.test_ajustements import PROVISION


def test_rev26_note_de_synthese(client, rev):  # noqa: F811
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    aud, chef = rev["aud"].headers, rev["chef"].headers
    load(client, rev, f["id"])
    note = client.get(f"{base}/synthesis", headers=aud).json()
    assert {
        "vue": "planification",
        "texte": "Seuil de signification non fixé ou revue analytique impossible",
    } in note["points_en_suspens"]
    client.put(
        f"{base}/materiality",
        headers=chef,
        json={
            "base_seuil": "total_bilan",
            "pct_seuil": "1.5",
            "justification": "Total du bilan retenu",
        },
    )
    accepted = client.post(f"{base}/adjustments", json=PROVISION, headers=aud).json()
    client.post(
        f"/api/adjustments/{accepted['id']}/decision", json={"statut": "acceptee"}, headers=aud
    )
    client.post(
        f"{base}/adjustments", json={**PROVISION, "libelle": "Autre dépréciation"}, headers=aud
    )
    conf = client.post(
        f"{base}/confirmations",
        json={"type": "client", "tiers": "Client A", "solde_comptable": "1000"},
        headers=aud,
    ).json()
    client.patch(f"/api/confirmations/{conf['id']}", json={"statut": "envoyee"}, headers=aud)
    note = client.get(f"{base}/synthesis", headers=aud).json()
    by_view = {p["vue"] for p in note["points_en_suspens"]}
    assert by_view == {"analytique", "circularisation", "tresorerie", "ajustements"}
    clients = next(c for c in note["cycles"] if c["cycle"] == "Clients et cotisants")
    assert (clients["N"], clients["ajustements"], clients["revise"]) == (
        "6700000.00",
        "-500000.00",
        "6200000.00",
    )
    assert note["ajustements_acceptes"] == [
        {"numero": 1, "libelle": PROVISION["libelle"], "effet_resultat": "-500000.00"}
    ]
    assert (
        note["non_corrigees"]["cumul_resultat"] == "-500000.00"
        and note["non_corrigees"]["conclusion"] == "significatif"
    )
    # Conclusion rédigée par le chef de mission.
    body = {
        "conclusion": "Sous réserve de la dépréciation non comptabilisée, les comptes sont réguliers."
    }
    assert client.put(f"{base}/synthesis/conclusion", json=body, headers=aud).status_code == 403
    assert (
        client.put(f"{base}/synthesis/conclusion", json=body, headers=chef).json()["conclusion"]
        == body["conclusion"]
    )
    pdf = client.get(f"{base}/synthesis/export?format=pdf", headers=aud)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    word = client.get(f"{base}/synthesis/export?format=docx", headers=aud)
    text = "\n".join(p.text for p in Document(io.BytesIO(word.content)).paragraphs)
    assert "4. Points en suspens" in text and "Sous réserve de la dépréciation" in text
    assert "AJE 1 — Dépréciation de la créance Alpha" in text
