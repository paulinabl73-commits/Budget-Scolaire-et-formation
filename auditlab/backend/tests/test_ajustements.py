"""REV-21 : propositions d'écritures d'ajustement."""

from decimal import Decimal

from app.models import AuditFile, Workpaper
from app.revision.mapping import file_values
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_affectation import load

PROVISION = {
    "type": "correction",
    "libelle": "Dépréciation de la créance Alpha",
    "justification": "Client en redressement judiciaire depuis novembre (jugement du 12/11).",
    "lignes": [
        {"compte": "681300", "libelle": "Dotation", "debit": "500000"},
        {"compte": "491000", "libelle": "Dépréciation clients", "credit": "500000"},
    ],
}


def test_rev21_ajustements(client, rev, db):  # noqa: F811
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}/adjustments"
    aud = rev["aud"].headers
    load(client, rev, f["id"])
    wp = Workpaper(engagement_id=rev["mission"]["id"], reference="C-1", titre="Clients",
                   travaux={"type": "doc", "content": []})  # fmt: skip
    db.add(wp)
    db.commit()
    # Contrôles : équilibre, comptes du plan, un seul sens par ligne, décimales, papier.
    bad = [
        {
            "lignes": [
                {"compte": "681300", "debit": "500000"},
                {"compte": "491000", "credit": "400000"},
            ]
        },
        {
            "lignes": [
                {"compte": "681300", "debit": "500000"},
                {"compte": "001000", "credit": "500000"},
            ]
        },
        {
            "lignes": [
                {"compte": "681300", "debit": "5", "credit": "5"},
                {"compte": "491000", "credit": "0"},
            ]
        },
        {"lignes": [{"compte": "681300", "debit": "0.5"}, {"compte": "491000", "credit": "0.5"}]},
        {"workpaper_id": "00000000-0000-0000-0000-000000000000"},
        {"justification": "court"},
    ]
    for change in bad:
        assert client.post(url, json={**PROVISION, **change}, headers=aud).status_code == 422, (
            change
        )
    assert client.post(url, json=PROVISION, headers=rev["da"].headers).status_code == 403
    adj = client.post(url, json={**PROVISION, "workpaper_id": str(wp.id)}, headers=aud).json()
    assert (adj["numero"], adj["statut"], adj["total"], adj["effet_resultat"]) == (
        1, "proposee", "500000.00", "-500000.00")  # fmt: skip
    reclass = {"type": "reclassement", "libelle": "Avances clients en passif",
               "justification": "Avance reçue présentée à tort en diminution des clients.",
               "lignes": [{"compte": "411100", "debit": "300000"}, {"compte": "419100", "credit": "300000"}]}  # fmt: skip
    second = client.post(url, json=reclass, headers=aud).json()
    assert second["numero"] == 2 and second["effet_resultat"] == "0.00"
    # Modification tant que proposée ; suppression d'une proposition.
    changed = client.put(f"/api/adjustments/{second['id']}", json={**reclass, "libelle": "Reclassement avances"},
                         headers=aud).json()  # fmt: skip
    assert changed["libelle"] == "Reclassement avances" and len(changed["lignes"]) == 2
    # Décision de l'entité : le refus doit être motivé ; une décision fige l'écriture.
    resp = client.post(
        f"/api/adjustments/{adj['id']}/decision", json={"statut": "refusee"}, headers=aud
    )
    assert resp.status_code == 422
    decided = client.post(
        f"/api/adjustments/{adj['id']}/decision", json={"statut": "acceptee"}, headers=aud
    ).json()
    assert decided["statut"] == "acceptee" and decided["decision_par"] and decided["decision_le"]
    assert client.post(f"/api/adjustments/{adj['id']}/decision", json={"statut": "refusee", "motif": "x"},
                       headers=aud).status_code == 409  # fmt: skip
    assert (
        client.put(f"/api/adjustments/{adj['id']}", json=PROVISION, headers=aud).status_code == 409
    )
    assert client.delete(f"/api/adjustments/{adj['id']}", headers=aud).status_code == 409
    refused = client.post(f"/api/adjustments/{second['id']}/decision",
                          json={"statut": "refusee", "motif": "Présentation conservée par la direction"},
                          headers=aud).json()  # fmt: skip
    assert refused["motif_decision"].startswith("Présentation")
    third = client.post(url, json=PROVISION, headers=aud).json()
    assert client.delete(f"/api/adjustments/{third['id']}", headers=aud).status_code == 204
    assert client.delete(f"/api/adjustments/{third['id']}", headers=aud).status_code == 404
    listed = client.get(url, headers=rev["chef"].headers).json()
    assert [(a["numero"], a["statut"]) for a in listed] == [(1, "acceptee"), (2, "refusee")]
    # Soldes révisés : seule l'écriture acceptée est prise en compte.
    file = db.get(AuditFile, f["id"])
    before, after = file_values(db, file)["N"], file_values(db, file, adjusted=True)["N"]
    assert before["BI"] == Decimal("7000000") and after["BI"] == Decimal("6500000")
    assert after["XI"] == before["XI"] - 500000 and after["BZ"] == after["DZ"]
