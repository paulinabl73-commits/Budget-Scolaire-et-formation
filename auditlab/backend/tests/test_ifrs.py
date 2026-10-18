"""IFR-01 et IFR-03 : retraitements IFRS datés et rattachés à une norme, table de passage,
états IFRS et réconciliations des capitaux propres et du résultat."""

import io

from docx import Document

from app.revision.frameworks import builtin, load_framework
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load

IFRS16 = {
    "type": "retraitement_ifrs",
    "norme": "IFRS 16",
    "date_ecriture": "2026-12-31",
    "libelle": "Location du véhicule de direction (contrat de 5 ans)",
    "justification": "Droit d'utilisation et dette de location ; annulation du loyer de l'exercice.",
    "lignes": [
        {"compte": "245100", "debit": "1000000"},
        {"compte": "172000", "credit": "1000000"},
        {"compte": "172000", "debit": "190000"},
        {"compte": "671000", "debit": "60000"},
        {"compte": "622000", "credit": "250000"},
        {"compte": "681300", "debit": "200000"},
        {"compte": "284510", "credit": "200000"},
    ],
}
IAS19 = {
    "type": "retraitement_ifrs",
    "norme": "IAS 19",
    "date_ecriture": "2026-12-31",
    "libelle": "Indemnités de fin de carrière",
    "justification": "Engagement non provisionné en SYSCOHADA.",
    "lignes": [{"compte": "661000", "debit": "300000"}, {"compte": "196000", "credit": "300000"}],
}


def test_ifr01_ifr03_passage_aux_ifrs(client, rev, db):  # noqa: F811
    load_framework(db, builtin("ifrs_2024"))
    db.commit()
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    aud = rev["aud"].headers
    load(client, rev, f["id"])
    # Un retraitement est daté et rattaché à une norme.
    bad = {**IAS19, "norme": None}
    assert client.post(f"{base}/adjustments", json=bad, headers=aud).status_code == 422
    ids = [
        client.post(f"{base}/adjustments", json=e, headers=aud).json()["id"]
        for e in (IFRS16, IAS19)
    ]
    data = client.get(f"{base}/ifrs", headers=aud).json()
    assert [r["norme"] for r in data["retraitements"]] == ["IFRS 16", "IAS 19"]
    assert data["reconciliation"]["resultat"]["ifrs"] == "7100000.00"  # non encore validés
    for i in ids:
        client.post(f"/api/adjustments/{i}/decision", json={"statut": "acceptee"}, headers=aud)
    data = client.get(f"{base}/ifrs", headers=aud).json()
    assert list(data["etats"]) == ["ifrs_situation", "ifrs_resultat", "ifrs_capitaux", "ifrs_flux"]
    situation = {x["code"]: x for x in data["etats"]["ifrs_situation"]}
    resultat = {x["code"]: x for x in data["etats"]["ifrs_resultat"]}
    assert situation["IZZ"]["N"] == situation["IPZ"]["N"] and situation["ID2"]["N"] == "810000.00"
    assert situation["IA2"]["passage"] == "AJ+AK+AM+AN"
    assert resultat["IRN"]["N"] == "6790000.00" and resultat["IRN"]["N-1"] == "1500000.00"
    assert all(c["ok"] for c in data["controles"]), data["controles"]
    capitaux = {x["code"]: x for x in data["etats"]["ifrs_capitaux"]}
    assert capitaux["IV4"]["N"] == "19790000.00" and capitaux["IV1"]["N-1"] is None
    rec = data["reconciliation"]
    assert [(r["libelle"], r["montant"]) for r in rec["capitaux"]["lignes"]] == [
        ("Capitaux propres SYSCOHADA révisés", "20100000.00"),
        ("Retraitements IAS 19", "-300000.00"),
        ("Retraitements IFRS 16", "-10000.00"),
        ("Subventions d'investissement présentées en produits différés (IAS 20)", "0"),
    ]
    assert rec["capitaux"]["ecart"] == "0.00" and rec["resultat"]["ecart"] == "0.00"
    # Les retraitements n'affectent ni les états SYSCOHADA révisés ni les anomalies (REV-22).
    syscohada = client.get(f"{base}/statements", headers=aud).json()["etats"]["compte_resultat"]
    assert next(x for x in syscohada if x["code"] == "XI")["N"] == "7100000.00"
    assert client.get(f"{base}/adjustments", headers=aud).json() == []
    text = "\n".join(
        p.text
        for p in Document(
            io.BytesIO(client.get(f"{base}/ifrs/export?format=docx", headers=aud).content)
        ).paragraphs
    )
    assert "États financiers IFRS – exercice 2026" in text
