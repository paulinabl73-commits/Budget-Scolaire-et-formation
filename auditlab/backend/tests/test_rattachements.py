"""RCO-13 : rattachement des charges et produits à l'exercice, reprise à l'ouverture de N+1."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco13_rattachements(client, cabinet):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    c = new_client(client, cabinet)
    fid = open_closing(client, cabinet, c, 2025)["audit_file_id"]
    url = f"/api/audit-files/{fid}/accruals"
    items = [
        {"type": "charge_a_payer", "libelle": "Électricité de décembre", "compte_gestion": "605100", "montant": "150000"},
        {"type": "produit_a_recevoir", "libelle": "Livraison non facturée", "compte_gestion": "701000", "montant": "80000"},
        {"type": "charge_constatee_avance", "libelle": "Assurance annuelle", "compte_gestion": "625000",
         "montant_total": "1200000", "periode_debut": "2025-07-01", "periode_fin": "2026-06-30"},
    ]  # fmt: skip
    for item in items:
        data = client.post(url, json=item, headers=collab.headers).json()
    assert data["comptes_proposes"]["charge_a_payer"] == "408"
    cca = next(e for e in data["elements"] if e["type"] == "charge_constatee_avance")
    assert (cca["montant"], cca["compte_tiers"]) == ("595068.00", "476")  # 181 jours sur 365
    assert data["totaux"]["charge_a_payer"] == "150000.00"
    assert (
        client.post(url, json={**items[0], "montant": None}, headers=collab.headers).status_code
        == 422
    )
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    lines = {(ln["compte"], "D" if ln["debit"] != "0.00" else "C"): ln["debit"] if ln["debit"] != "0.00" else ln["credit"]
             for ln in entry["lignes"]}  # fmt: skip
    assert lines == {("605100", "D"): "150000.00", ("408", "C"): "150000.00", ("418", "D"): "80000.00",
                     ("701000", "C"): "80000.00", ("476", "D"): "595068.00", ("625000", "C"): "595068.00"}  # fmt: skip
    # Reprise à l'ouverture de N+1 : proposée automatiquement une fois l'écriture acceptée.
    client.post(
        f"/api/adjustments/{entry['id']}/decision",
        json={"statut": "acceptee"},
        headers=expert.headers,
    )
    next_fid = open_closing(client, cabinet, c, 2026)["audit_file_id"]
    [reprise] = client.get(
        f"/api/audit-files/{next_fid}/adjustments", headers=collab.headers
    ).json()
    assert reprise["origine"] == "RCO-13-reprise" and reprise["date_ecriture"] == "2026-01-01"
    back = {(ln["compte"], "D" if ln["debit"] != "0.00" else "C") for ln in reprise["lignes"]}
    assert ("408", "D") in back and ("605100", "C") in back and ("476", "C") in back
    again = client.post(f"/api/audit-files/{next_fid}/accruals/reversal", headers=collab.headers)
    assert again.status_code == 201 and again.json()["origine"] == "RCO-13-reprise"
    assert (
        client.post(f"/api/audit-files/{fid}/accruals/reversal", headers=collab.headers).status_code
        == 409
    )
