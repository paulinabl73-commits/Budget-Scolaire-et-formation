"""RCO-18 et RCO-19 : chiffre d'affaires et TVA comptabilisés et déclarés, mois par mois."""

from tests.portfolio_helpers import cabinet, new_client, open_closing  # noqa: F401
from tests.test_balances import upload
from tests.test_controles_comptables import files

RETURNS = """Période;CA déclaré;TVA collectée;TVA déductible;Crédit reporté
01/2026;0;0;0;0
mars 2026;300 000;54 000;7 200;0
2026-04;0;0;0;0
"""


def closing_with_ledger(client, cab):
    collab = cab["collab"]
    fid = open_closing(client, cab, new_client(client, cab))["audit_file_id"]
    balance, ledger = files()
    for name, content, kind in (("b.csv", balance, "balance"), ("gl.csv", ledger, "grand_livre")):
        assert (
            upload(client, {"aud": collab}, fid, name, content, type=kind).json()["statut"]
            == "accepte"
        )
    return fid


def test_rco18_chiffre_affaires(client, cabinet):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    fid = closing_with_ledger(client, cabinet)
    url = f"/api/audit-files/{fid}/turnover-reconciliation"
    assert client.get(url, headers=collab.headers).json()["mois_sans_declaration"][0] == "2026-01"
    resp = client.post(f"/api/audit-files/{fid}/tax-returns", files={"file": ("tva.csv", RETURNS.encode())},
                       headers=collab.headers)  # fmt: skip
    assert resp.json()["lignes"] == 3
    data = client.get(url, headers=collab.headers).json()
    march = next(m for m in data["mois"] if m["mois"] == "2026-03")
    assert (march["comptable"], march["declare"], march["ecart"], march["concordant"]) == (
        "310000.00", "300000", "10000.00", False)  # fmt: skip
    assert next(m for m in data["mois"] if m["mois"] == "2026-01")["concordant"]
    assert len(data["mois"]) == 12 and "2026-02" in data["mois_sans_declaration"]
    assert data["ecart_total"] == "10000.00"
    # Écart toléré : paramètre fiscal du pays.
    body = {"pays": "CI", "code": "tolerance_rapprochement", "valeur": "10000"}
    client.post("/api/fiscal-parameters", json=body, headers=expert.headers)
    march = next(
        m for m in client.get(url, headers=collab.headers).json()["mois"] if m["mois"] == "2026-03"
    )
    assert march["concordant"]
    bad = "Période;CA déclaré\ntreizième;1\n"
    assert client.post(f"/api/audit-files/{fid}/tax-returns", files={"file": ("t.csv", bad.encode())},
                       headers=collab.headers).status_code == 422  # fmt: skip
