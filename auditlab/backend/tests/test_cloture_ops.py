"""RCO-16 : cotisations à recevoir, prestations à payer, provisions techniques par branche."""

from tests.cipres_helpers import DETAIL_N, DETAIL_N1, balance_csv, ops_detail, set_params  # noqa: F401
from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload


def test_rco16_cloture_ops(client, cabinet, ops_detail, db):  # noqa: F811
    collab = cabinet["collab"]
    c = new_client(client, cabinet, raison_sociale="Caisse de prévoyance", forme_juridique="OPS",
                   framework_id=str(ops_detail.id))  # fmt: skip
    fid = open_closing(client, cabinet, c)["audit_file_id"]
    opening = {k: v for k, v in DETAIL_N1.items() if k[0] in "12345"}
    for periode, content in (
        ("N-1", balance_csv(DETAIL_N1)),
        ("N", balance_csv(DETAIL_N, opening)),
    ):
        assert (
            upload(client, {"aud": collab}, fid, "b.csv", content, periode=periode).json()["statut"]
            == "accepte"
        )
    url = f"/api/audit-files/{fid}/ops-closing"
    items = [
        {"nature": "cotisations_a_recevoir", "branche": "PF", "libelle": "Cotisations de décembre",
         "compte_debit": "411", "compte_credit": "701", "montant": "3000000"},
        {"nature": "prestations_a_payer", "branche": "PV", "libelle": "Pensions liquidées non payées",
         "compte_debit": "633", "compte_credit": "411", "montant": "1500000"},
        {"nature": "provision_technique", "branche": "PF", "libelle": "Réserve technique",
         "compte_debit": "631", "compte_credit": "1511", "compte_reprise": "771"},
        {"nature": "provision_technique", "branche": "PV", "libelle": "Réserve technique",
         "compte_debit": "633", "compte_credit": "1513", "compte_reprise": "771"},
    ]  # fmt: skip
    for item in items:
        assert client.post(url, json=item, headers=collab.headers).status_code == 201
    assert (
        client.post(url, json={**items[0], "branche": "ZZ"}, headers=collab.headers).status_code
        == 422
    )
    data = client.get(url, headers=collab.headers).json()
    assert (
        data["parametres_manquants"]
        and client.post(f"{url}/entry", headers=collab.headers).status_code == 409
    )
    set_params(
        db,
        ops_detail,
        ("reserve_technique_mois", "6", "PF"),
        ("reserve_technique_mois", "12", "PV"),
    )
    data = client.get(url, headers=collab.headers).json()
    reserves = {r["branche"]: r for r in data["provisions_techniques"]}
    assert (reserves["PF"]["requise"], reserves["PF"]["ecart"]) == ("12000000", "2000000.00")
    assert reserves["PV"]["ecart"] == "-18000000.00"  # réserve excédentaire : reprise
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    moves = {(ln["compte"], "D" if ln["debit"] != "0.00" else "C"): ln for ln in entry["lignes"]}
    assert (
        moves[("1511", "C")]["credit"] == "2000000.00"
        and moves[("1513", "D")]["debit"] == "18000000.00"
    )
    assert moves[("771", "C")]["credit"] == "18000000.00" and entry["origine"] == "RCO-16"
