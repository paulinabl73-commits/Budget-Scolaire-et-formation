"""RCO-12 : inventaire physique, valorisation (CMP, PEPS), dépréciation, variation de stock."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload

BALANCE = """Compte;Intitulé;Solde débit;Solde crédit
101000;Capital;;1000000
311000;Marchandises;500000;
391000;Dépréciation des marchandises;;20000
521000;Banque;520000;
"""
INVENTORY = "Référence;Désignation;Compte;Quantité;VNR\nA1;Farine;311000;10;18 000\nA2;Sucre;311000;5;5 000\n"
MOVEMENTS = """Article;Date;Nature;Quantité;Prix unitaire
A1;01/01/2026;Initial;20;15 000
A1;15/03/2026;Achat;30;20 000
A1;20/09/2026;Achat;10;22 000
A2;01/01/2026;Initial;10;8 000
A2;10/06/2026;Achat;20;9 000
"""


def test_rco12_stocks(client, cabinet):  # noqa: F811
    collab = cabinet["collab"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    assert (
        upload(client, {"aud": collab}, fid, "b.csv", BALANCE.encode()).json()["statut"]
        == "accepte"
    )
    url = f"/api/audit-files/{fid}/stock"
    data = client.post(
        f"{url}/files/inventory", files={"file": ("inv.csv", INVENTORY.encode())}, headers=collab.headers
    ).json()
    assert data["non_valorises"] == ["A1", "A2"]  # entrées pas encore importées
    data = client.post(
        f"{url}/files/movements", files={"file": ("e.csv", MOVEMENTS.encode())}, headers=collab.headers
    ).json()
    arts = {a["article"]: a for a in data["articles"]}
    assert (arts["A1"]["valeur"], arts["A1"]["depreciation"]) == ("186667", "6667")
    assert (arts["A2"]["valeur"], arts["A2"]["depreciation"]) == ("43333", "18333")
    assert data["comptes"] == [{"compte": "311000", "stock_final": "230000", "solde_comptable": "500000.00",
                                "variation": "-270000.00"}]  # fmt: skip
    assert data["depreciations"][0]["ecart"] == "5000.00"
    peps = client.put(f"{url}/method", json={"methode": "peps"}, headers=collab.headers).json()
    assert {a["article"]: a["valeur"] for a in peps["articles"]} == {"A1": "220000", "A2": "45000"}
    client.put(f"{url}/method", json={"methode": "cmp"}, headers=collab.headers)
    entry = client.post(f"{url}/entry", headers=collab.headers).json()
    assert "lignes" in entry, entry
    lines = {(ln["compte"], "D" if ln["debit"] != "0.00" else "C"): ln for ln in entry["lignes"]}
    assert (
        lines[("6031", "D")]["debit"] == "270000.00"
        and lines[("311000", "C")]["credit"] == "270000.00"
    )
    assert lines[("6593", "D")]["debit"] == "5000.00" and entry["origine"] == "RCO-12"
    bad = "Article;Compte;Quantité\nZ;999;1\n"
    data = client.post(
        f"{url}/files/inventory", files={"file": ("i.csv", bad.encode())}, headers=collab.headers
    ).json()
    assert data["non_valorises"] == ["Z"]
    assert client.post(f"{url}/entry", headers=collab.headers).status_code == 409
    assert (
        client.post(
            f"{url}/files/inventory", files={"file": ("i.csv", b"x;y\n1;2\n")}, headers=collab.headers
        ).status_code
        == 422
    )
