"""REV-18 : lettrage et justification des comptes de tiers, balance âgée, dépréciation."""

from collections import defaultdict

from tests.revision_helpers import create_file, rev  # noqa: F401
from tests.test_balances import upload

# (date, journal, pièce, compte, débit, crédit, tiers, lettrage)
LINES = [
    ("02/01/2026", "VT", "F1", "411100", 1180000, 0, "A", "A1"),
    ("15/02/2026", "BQ", "R1", "411100", 0, 1180000, "A", "A1"),
    ("10/03/2026", "VT", "F2", "411100", 590000, 0, "A", ""),
    ("20/11/2026", "VT", "F3", "411100", 236000, 0, "B", ""),
    ("20/12/2026", "BQ", "R3", "411100", 0, 100000, "B", ""),
    ("01/06/2026", "VT", "F4", "411100", 118000, 0, "C", "C9"),
    ("01/07/2026", "BQ", "R4", "411100", 0, 100000, "C", "C9"),  # lettrage déséquilibré
    ("01/04/2026", "AC", "FA1", "401100", 0, 354000, "S", ""),
    ("01/05/2026", "BQ", "P1", "401100", 354000, 0, "S", ""),
    ("15/12/2026", "AC", "FA2", "401100", 0, 200000, "S", ""),
]


def ledger_and_balance() -> tuple[bytes, bytes]:
    rows = []
    for date, journal, piece, compte, debit, credit, tiers, code in LINES:
        rows.append((date, journal, piece, compte, debit, credit, tiers, code))
        counterpart = {"VT": "701100", "BQ": "521100", "AC": "601100"}[journal]
        rows.append((date, journal, piece, counterpart, credit, debit, "", ""))
    gl = ["Date;Journal;N° pièce;Compte;Libellé;Débit;Crédit;Code tiers;Lettrage"]
    totals: dict[str, int] = defaultdict(int)
    for date, journal, piece, compte, debit, credit, tiers, code in rows:
        gl.append(
            f"{date};{journal};{piece};{compte};Pièce {piece};{debit or ''};{credit or ''};{tiers};{code}"
        )
        totals[compte] += debit - credit
    bal = ["Compte;Intitulé;Mouvements débit;Mouvements crédit"]
    for compte, net in sorted(totals.items()):
        bal.append(f"{compte};Compte {compte};{max(net, 0)};{max(-net, 0)}")
    return ("\n".join(gl) + "\n").encode(), ("\n".join(bal) + "\n").encode()


def test_rev18_tiers_balance_agee_depreciation(client, rev):  # noqa: F811
    f = create_file(client, rev)
    base = f"/api/audit-files/{f['id']}"
    aud, chef = rev["aud"].headers, rev["chef"].headers
    assert client.get(f"{base}/third-parties", headers=aud).status_code == 409
    gl, bal = ledger_and_balance()
    assert upload(client, rev, f["id"], "bal.csv", bal).json()["statut"] == "accepte"
    tb = upload(client, rev, f["id"], "gl.csv", gl, type="grand_livre").json()
    assert tb["statut"] == "accepte", tb["anomalies"]
    # Justification : lettrage fourni (clients) ou automatique (fournisseurs).
    just = client.get(f"{base}/third-parties", headers=aud).json()
    comptes = {c["compte"]: c for c in just["comptes"]}
    assert just["non_justifies"] == 0
    clients, fournisseurs = comptes["411100"], comptes["401100"]
    assert (clients["mode"], clients["lettrees"], clients["ouvertes"]) == ("fourni", 2, 5)
    assert clients["anomalies"] == ["Lettrage « C9 » déséquilibré"]
    assert clients["solde_ouvert"] == clients["solde_balance"] == "744000.00"
    assert (fournisseurs["mode"], fournisseurs["lettrees"], fournisseurs["ouvertes"]) == (
        "automatique",
        2,
        1,
    )
    assert fournisseurs["lignes_ouvertes"][0]["piece"] == "FA2"
    # Balance âgée (grille par défaut : 0 %, 25 % au-delà de 180 jours, 50 %, 100 %).
    aging = client.get(f"{base}/receivables-aging", headers=aud).json()
    assert [t["libelle"] for t in aging["tranches"]] == ["0 à 180 jours", "181 à 365 jours",
                                                        "366 à 730 jours", "731 jours et plus"]  # fmt: skip
    assert aging["totaux"] == ["136000", "608000", "0", "0"]
    parties = {t["tiers"]: t for t in aging["tiers"]}
    assert parties["A"]["depreciation"] == "147500" and parties["C"]["depreciation"] == "4500"
    assert parties["B"]["tranches"][0] == "136000" and parties["B"]["depreciation"] == "0"
    assert (aging["depreciation_requise"], aging["depreciation_comptabilisee"], aging["ecart"]) == (
        "152000", "0", "152000")  # fmt: skip
    # Écriture proposée pour l'écart, puis conformité une fois acceptée.
    adj = client.post(f"{base}/receivables-aging/adjustment", headers=aud).json()
    assert adj["montant"] == "152000"
    client.post(f"/api/adjustments/{adj['id']}/decision", json={"statut": "acceptee"}, headers=aud)
    assert client.get(f"{base}/receivables-aging", headers=aud).json()["ecart"] == "0"
    assert client.post(f"{base}/receivables-aging/adjustment", headers=aud).status_code == 409
    # Grille du dossier : base hors taxes (TVA 18 %), réservée au chef de mission.
    grid = {"grille": [[0, 0], [181, 25], [366, 50], [731, 100]], "tva_pct": "18"}
    assert client.put(f"{base}/impairment-grid", json=grid, headers=aud).status_code == 403
    for bad in ([[10, 0]], [[0, 0], [0, 10]], [[0, 120]]):
        assert (
            client.put(f"{base}/impairment-grid", json={"grille": bad}, headers=chef).status_code
            == 422
        )
    aging = client.put(f"{base}/impairment-grid", json=grid, headers=chef).json()
    assert aging["depreciation_requise"] == "128814" and aging["ecart"] == "-23186"
    reprise = client.post(f"{base}/receivables-aging/adjustment", headers=aud).json()
    lines = next(
        a for a in client.get(f"{base}/adjustments", headers=aud).json() if a["id"] == reprise["id"]
    )["lignes"]
    assert [(ln["compte"], ln["debit"], ln["credit"]) for ln in lines] == [
        ("491000", "23186.00", "0.00"), ("791000", "0.00", "23186.00")]  # fmt: skip
