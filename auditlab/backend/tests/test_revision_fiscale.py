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


VAT_ENTRIES = [  # date, journal, pièce, [(compte, débit, crédit)]
    ("01/01/2026", "BQ", "B1", [("521000", 2_000_000, 0), ("101000", 0, 2_000_000)]),
    ("14/03/2026", "VT", "V1", [("411100", 354_000, 0), ("701000", 0, 300_000), ("443100", 0, 54_000)]),
    ("20/03/2026", "AC", "A1", [("601000", 40_000, 0), ("445200", 7_200, 0), ("401100", 0, 47_200)]),
    ("15/04/2026", "OD", "O1", [("444900", 25_000, 0), ("521000", 0, 25_000)]),
]  # fmt: skip


def vat_files():
    from collections import defaultdict

    gl, net = ["Date;Journal;Pièce;Compte;Libellé;Débit;Crédit"], defaultdict(int)
    for date, journal, piece, lines in VAT_ENTRIES:
        for compte, d, c in lines:
            gl.append(f"{date};{journal};{piece};{compte};{piece};{d or ''};{c or ''}")
            net[compte] += d - c
    bal = ["Compte;Intitulé;Solde débit;Solde crédit"]
    bal += [f"{c};Compte {c};{max(v, 0) or ''};{max(-v, 0) or ''}" for c, v in sorted(net.items())]
    return ("\n".join(bal) + "\n").encode(), ("\n".join(gl) + "\n").encode()


def test_rco19_tva(client, cabinet):  # noqa: F811
    collab, expert = cabinet["collab"], cabinet["expert"]
    fid = open_closing(client, cabinet, new_client(client, cabinet))["audit_file_id"]
    balance, ledger = vat_files()
    for name, content, kind in (("b.csv", balance, "balance"), ("gl.csv", ledger, "grand_livre")):
        assert (
            upload(client, {"aud": collab}, fid, name, content, type=kind).json()["statut"]
            == "accepte"
        )
    returns = "Période;CA déclaré;TVA collectée;TVA déductible;Crédit reporté\n03/2026;300000;54000;7200;0\n04/2026;0;0;0;20000\n"
    client.post(
        f"/api/audit-files/{fid}/tax-returns",
        files={"file": ("t.csv", returns.encode())},
        headers=collab.headers,
    )
    url = f"/api/audit-files/{fid}/vat-reconciliation"
    data = client.get(url, headers=collab.headers).json()
    march = {
        k: next(m for m in data[k] if m["mois"] == "2026-03") for k in ("collectee", "deductible")
    }
    assert (march["collectee"]["comptable"], march["collectee"]["concordant"]) == ("54000.00", True)
    assert (march["deductible"]["comptable"], march["deductible"]["concordant"]) == (
        "7200.00",
        True,
    )
    assert data["tva_theorique"] is None  # taux normal non saisi
    credit = data["credit_tva"]
    assert (credit["solde_comptable"], credit["credit_declare"], credit["ecart"], credit["justifie"]) == (
        "25000.00", "20000", "5000.00", False)  # fmt: skip
    client.post("/api/fiscal-parameters", json={"pays": "CI", "code": "taux_tva_normal", "valeur": "18"},
                headers=expert.headers)  # fmt: skip
    data = client.get(url, headers=collab.headers).json()
    assert (data["tva_theorique"], data["ecart_theorique"]) == ("54000.00", "0.00")
