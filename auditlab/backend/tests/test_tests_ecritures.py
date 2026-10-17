"""REV-17 : tests des écritures de journal sur le grand livre (Module 2)."""

from app.models import Dataset
from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload


def ledger() -> bytes:
    lines = ["Date;Journal;N° pièce;Compte;Libellé;Débit;Crédit;Utilisateur;Date saisie"]
    for i, day in enumerate(("15", "16", "17", "18"), start=1):  # du lundi au jeudi
        lines += [f"{day}/06/2026;VT;V{i};411100;Facture {i};118 500;;kouassi;{day}/06/2026",
                  f"{day}/06/2026;VT;V{i};701100;Facture {i};;118 500;kouassi;{day}/06/2026",
                  f"{day}/06/2026;AC;A{i};601100;Achat {i};75 250;;kouassi;{day}/06/2026",
                  f"{day}/06/2026;AC;A{i};401100;Achat {i};;75 250;kouassi;{day}/06/2026"]  # fmt: skip
    # Écriture d'opérations diverses saisie un samedi après la clôture, montant rond.
    lines += ["13/06/2026;OD;X1;471000;;500 000;;intrus;16/01/2027",
              "13/06/2026;OD;X1;521100;Virement;;500 000;intrus;16/01/2027"]  # fmt: skip
    return ("\n".join(lines) + "\n").encode()


def test_rev17_tests_des_ecritures(client, rev, db):  # noqa: F811
    f = create_file(client, rev)
    url = f"/api/audit-files/{f['id']}/journal-tests"
    aud = rev["aud"].headers
    assert client.post(url, json={}, headers=aud).status_code == 409  # pas de grand livre
    gl = upload(client, rev, f["id"], "gl.csv", ledger(), type="grand_livre").json()
    assert gl["statut"] == "accepte", gl["anomalies"]
    assert client.post(url, json={}, headers=rev["da"].headers).status_code == 403
    resp = client.post(url, json={}, headers=aud)
    assert resp.status_code == 202, resp.text
    result = db.get(Dataset, resp.json()["dataset_id"])
    db.refresh(result)
    assert result.statut == "pret" and result.operation == "ecritures_journal"
    assert result.parent_dataset_id is not None and result.nb_lignes == 2
    summary = result.resultat
    assert summary["lignes_source"] == 18 and summary["criteres_non_appliques"] == []
    assert summary["par_critere"] == {"manuelle": 2, "week_end": 2, "apres_cloture": 2, "montant_rond": 2,
                                      "compte_inhabituel": 2, "utilisateur_inhabituel": 2, "libelle_vide": 1}  # fmt: skip
    body = {"offset": 0, "limit": 10}
    page = client.post(f"/api/datasets/{result.id}/rows", json=body, headers=aud).json()
    first = dict(zip(page["colonnes"], page["lignes"][0], strict=True))
    assert first["compte"] == "471000" and first["nb_criteres"] == 7
    assert first["criteres"].startswith("manuelle, week_end, apres_cloture")
    # Seuils modifiables : un pas de 1 000 000 ne retient plus le montant rond.
    resp = client.post(
        url, json={"pas_montant_rond": "1000000", "journaux_manuels": "OD, AC"}, headers=aud
    )
    again = db.get(Dataset, resp.json()["dataset_id"])
    assert (
        again.resultat["par_critere"]["montant_rond"] == 0
        and again.resultat["par_critere"]["manuelle"] == 10
    )
