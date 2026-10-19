"""RCO-15 : écarts de conversion au cours de clôture et provision pour perte de change."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401


def test_rco15_ecarts_de_conversion(client, cabinet):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    url = f"/api/audit-files/{fid}/currency-positions"
    positions = [
        {"compte": "411200", "libelle": "Client export", "nature": "creance", "devise": "USD",
         "montant_devise": "1000", "valeur_comptable": "620000"},  # 600 000 à la clôture : perte 20 000
        {"compte": "401200", "libelle": "Fournisseur Europe", "nature": "dette", "devise": "USD",
         "montant_devise": "2000", "valeur_comptable": "1150000"},  # 1 200 000 : perte 50 000
        {"compte": "411300", "libelle": "Client export 2", "nature": "creance", "devise": "USD",
         "montant_devise": "500", "valeur_comptable": "280000"},  # 300 000 : gain 20 000
    ]  # fmt: skip
    for p in positions:
        data = client.post(url, json=p, headers=collab.headers).json()
    assert data["cours_manquants"] == ["USD"]
    assert client.post(f"{url}/entry", headers=collab.headers).status_code == 409
    rate = {"devise_source": "USD", "devise_cible": "XOF", "date": "2026-12-31", "taux": "600"}
    assert client.post("/api/exchange-rates", json=rate, headers=expert.headers).status_code == 201
    data = client.get(url, headers=collab.headers).json()
    assert (data["pertes_latentes"], data["gains_latents"], data["provision_requise"]) == (
        "70000.00",
        "20000.00",
        "70000.00",
    )
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    amounts = {}
    for ln in entry["lignes"]:
        amounts[ln["compte"]] = ln["debit"] if ln["debit"] != "0.00" else "-" + ln["credit"]
    assert amounts == {"478": "70000.00", "411200": "-20000.00", "401200": "-50000.00", "411300": "20000.00",
                       "479": "-20000.00", "697": "70000.00", "194": "-70000.00"}  # fmt: skip
    same = {**positions[0], "devise": "XOF"}
    assert client.post(url, json=same, headers=collab.headers).status_code == 422
