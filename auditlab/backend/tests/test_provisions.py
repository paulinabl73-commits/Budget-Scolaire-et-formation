"""RCO-14 : provisions et dépréciations (créances douteuses, litiges, risques)."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_controles_comptables import files


def test_rco14_provisions(client, cabinet):  # noqa: F811
    collab = cabinet["collab"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    balance, ledger = files()
    for name, content, kind in (("b.csv", balance, "balance"), ("gl.csv", ledger, "grand_livre")):
        assert (
            upload(client, {"aud": collab}, fid, name, content, type=kind).json()["statut"]
            == "accepte"
        )
    url = f"/api/audit-files/{fid}/provisions"
    data = client.get(url, headers=collab.headers).json()
    assert data["creances"]["ecart"] == "77500"  # 310 000 (411 et 419 débiteur) à 25 %
    assert data["comptes_proposes"]["litige"]["provision"] == "191"
    client.post(url, json={"nature": "litige", "libelle": "Prud'hommes ancien salarié", "montant_requis": "500000"},
                headers=collab.headers)  # fmt: skip
    data = client.post(url, json={"nature": "risque", "libelle": "Garantie clients", "montant_requis": "120000"},
                       headers=collab.headers).json()  # fmt: skip
    comptes = {a["compte"]: a for a in data["comptes"]}
    assert comptes["191"]["ecart"] == "500000.00" and comptes["198"]["comptabilise"] == "0"
    bad = {"nature": "autre", "libelle": "X", "montant_requis": "1", "compte_provision": "012"}
    assert client.post(url, json=bad, headers=collab.headers).status_code == 422
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    totals = {}
    for ln in entry["lignes"]:
        totals[ln["compte"]] = ln["debit"] if ln["debit"] != "0.00" else "-" + ln["credit"]
    assert (
        totals["691"] == "620000.00"
        and totals["191"] == "-500000.00"
        and totals["198"] == "-120000.00"
    )
    assert totals["691000"] == "77500.00" and totals["491000"] == "-77500.00"
    assert entry["origine"] == "RCO-14"
    prov = data["provisions"][0]["id"]
    assert client.delete(f"{url}/{prov}", headers=collab.headers).status_code == 204
