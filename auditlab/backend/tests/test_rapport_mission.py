"""REP-02 : génération du rapport de mission en PDF et Word."""

import io

import pytest
from docx import Document

from app.reporting import templates
from tests.finding_helpers import create_finding, team  # noqa: F401
from tests.report_helpers import validated_finding


@pytest.fixture
def modele(db):
    t = templates.seed(db)
    db.commit()
    return t


def _text(content):
    doc = Document(io.BytesIO(content))
    cells = [c.text for t in doc.tables for row in t.rows for c in row.cells]
    return "\n".join([p.text for p in doc.paragraphs] + cells)


def test_rep02_rapport(client, team, modele):  # noqa: F811
    chef, aud = team["chef"].headers, team["aud"].headers
    validated_finding(client, team, "moyenne", "Retards de facturation")
    validated_finding(client, team, "critique", "Paiements sans pièce")
    create_finding(client, team, titre="Constat encore en brouillon")
    url = f"{team['url']}/report"
    report = client.get(url, headers=aud).json()
    assert report["modele"] == modele.nom and report["peut_rediger"]
    body = {
        "synthese": "Le contrôle interne des achats est insuffisant.",
        "conclusion": "Plan à suivre.",
    }
    assert client.put(url, json=body, headers=team["da"].headers).status_code == 403
    assert client.put(url, json=body, headers=chef).json()["synthese"].startswith("Le contrôle")
    docx = client.get(f"{url}/document?format=docx", headers=team["directeur"].headers)
    assert docx.status_code == 200
    text = _text(docx.content)
    for expected in ("Rapport d'audit interne", "Diffusion restreinte", "Le contrôle interne",
                     "Criticité : Critique", "Accord partiel : 8 créations", "Réactiver le blocage",
                     "PROJET – constats en phase contradictoire non repris", "Papiers de travail"):  # fmt: skip
        assert expected in text, expected
    assert "Constat encore en brouillon" not in text.split("PROJET")[0]
    # Ordre par criticité décroissante : le constat critique précède le constat moyen.
    assert text.index("Paiements sans pièce") < text.index("Retards de facturation")
    pdf = client.get(f"{url}/document", headers=chef)
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_rep02_logo(client, team, modele):  # noqa: F811
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (120, 40), (31, 95, 168)).save(buf, format="PNG")
    client.put(f"/api/mission-report-templates/{modele.id}/logo",
               files={"file": ("logo.png", io.BytesIO(buf.getvalue()))}, headers=team["directeur"].headers)  # fmt: skip
    for fmt in ("pdf", "docx"):
        resp = client.get(
            f"{team['url']}/report/document?format={fmt}", headers=team["chef"].headers
        )
        assert resp.status_code == 200, fmt
    doc = Document(io.BytesIO(resp.content))
    assert len(doc.inline_shapes) == 1
