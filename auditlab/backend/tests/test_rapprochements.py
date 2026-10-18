"""REV-20 : rapprochements bancaires importés et contrôlés."""

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload
from tests.test_tiers import ledger_and_balance

SUSPENS = (
    "Date;Libellé;Référence;Origine;Montant\n"
    "15/08/2026;Remise de chèques non créditée;RC-12;Comptabilité;100 000\n"
    "28/12/2026;Chèque émis non encaissé;CH-881;Comptabilité;-294 000\n"
    "31/12/2026;Frais bancaires;FR-12;Relevé;20 000\n"
)


def post(client, rev, file_id, solde, content=SUSPENS, compte="521100"):  # noqa: F811
    files = {"file": ("suspens.csv", content.encode())} if content is not None else None
    return client.post(
        f"/api/audit-files/{file_id}/bank-reconciliations",
        files=files,
        data={"compte": compte, "solde_releve": solde},
        headers=rev["aud"].headers,
    )


def test_rev20_rapprochements_bancaires(client, rev):  # noqa: F811
    f = create_file(client, rev)
    gl, bal = ledger_and_balance()
    upload(client, rev, f["id"], "bal.csv", bal)  # banque 521100 : 1 026 000 au débit
    url = f"/api/audit-files/{f['id']}/bank-reconciliations"
    assert client.get(url, headers=rev["aud"].headers).json()["comptes_sans_rapprochement"] == [
        "521100"
    ]
    assert post(client, rev, f["id"], "1000", compte="411100").status_code == 422
    bad = "Date;Origine;Montant\n01/12/2026;Inconnue;10\n"
    assert post(client, rev, f["id"], "1000", content=bad).status_code == 422
    resp = post(client, rev, f["id"], "1 200 000")
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["comptes_sans_rapprochement"] == []
    rec = data["rapprochements"][0]
    assert (rec["solde_releve"], rec["solde_comptable"], rec["non_rapproche"]) == (
        "1200000.00",
        "1026000.00",
        "0.00",
    )
    assert rec["anomalies"] == [] and rec["suspens_anciens"] == 1
    assert rec["avertissements"] == ["1 suspens antérieur(s) au 02/10/2026",
                                     "Opérations passées par la banque seule, à comptabiliser à la clôture"]  # fmt: skip
    assert [s["ancien"] for s in rec["suspens"]] == [True, False, False]
    # Confirmation bancaire divergente, puis nouvel état non rapproché qui remplace le précédent.
    conf = client.post(f"/api/audit-files/{f['id']}/confirmations", headers=rev["aud"].headers,
                       json={"type": "banque", "tiers": "Banque Atlantique", "compte": "521100"}).json()  # fmt: skip
    client.patch(
        f"/api/confirmations/{conf['id']}",
        json={"solde_confirme": "1250000"},
        headers=rev["aud"].headers,
    )
    rec = client.get(url, headers=rev["aud"].headers).json()["rapprochements"][0]
    assert rec["anomalies"] == ["Solde du relevé différent du solde confirmé par la banque"]
    rec = post(client, rev, f["id"], "1250000").json()["rapprochements"]
    assert len(rec) == 1 and rec[0]["non_rapproche"] == "-50000.00"
    assert rec[0]["anomalies"] == ["Montant non rapproché : -50 000,00"]
    # Sans fichier de suspens : relevé seul.
    rec = post(client, rev, f["id"], "1026000", content=None).json()["rapprochements"][0]
    assert rec["suspens"] == [] and rec["non_rapproche"] == "0.00" and rec["nom_fichier"] is None
