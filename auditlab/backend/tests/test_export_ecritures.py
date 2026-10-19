"""RCO-17 : export des écritures générées au format du logiciel du client."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco17_export(client, cabinet):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    url = f"/api/audit-files/{fid}/accruals"
    client.post(url, json={"type": "charge_a_payer", "libelle": "Électricité de décembre", "compte_gestion": "605100",
                           "montant": "150000"}, headers=collab.headers)  # fmt: skip
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    export = f"/api/audit-files/{fid}/entries-export"
    assert client.get(export, headers=collab.headers).status_code == 409  # pas encore acceptée
    client.post(
        f"/api/adjustments/{entry['id']}/decision",
        json={"statut": "acceptee"},
        headers=expert.headers,
    )
    sage = client.get(f"{export}?format=sage&journal=OD", headers=collab.headers)
    assert (
        sage.status_code == 200 and "ecritures_2026_sage.txt" in sage.headers["content-disposition"]
    )
    rows = sage.content.decode("cp1252").splitlines()
    assert rows == [f"OD;311226;AJE{entry['numero']};605100;Électricité de décembre;150000,00;",
                    f"OD;311226;AJE{entry['numero']};408;Électricité de décembre;;150000,00"]  # fmt: skip
    odoo = client.get(f"{export}?format=odoo", headers=collab.headers).content.decode().splitlines()
    assert odoo[0].startswith("Journal,Date,Reference") and odoo[1].startswith("OD,2026-12-31,AJE")
    assert odoo[2].startswith(",,,408,")  # en-tête de pièce sur la première ligne seulement
    generic = client.get(export, headers=collab.headers).content.decode().splitlines()
    assert generic[0] == "Journal;Date;Pièce;Compte;Libellé;Débit;Crédit" and len(generic) == 3
    assert client.get(f"{export}?format=ciel", headers=collab.headers).status_code == 422
    assert [f["code"] for f in client.get("/api/entry-export-formats", headers=collab.headers).json()] == [
        "sage", "odoo", "generique"]  # fmt: skip
